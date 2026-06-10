"""
Audio playback for the Fotobox.

Backend strategy (most reliable backend first):
  * Sound effects (all formats)  libVLC one-shot players – one player per
                                  effect, so sounds may overlap. VLC goes
                                  through PipeWire/PulseAudio like the scene
                                  audio, so it cannot hit the "device busy"
                                  error that direct ALSA access (aplay) gets
                                  when the sound server holds the device.
  * SFX fallback (WAV, Linux) .. `aplay` subprocess – only used when libVLC
                                  is unavailable. Async failures are logged
                                  and a busy device disables the backend.
  * Background music ........... libVLC media player (WAV / MP3 / OGG).
  * Development fallback ....... QSoundEffect (macOS/Windows, WAV only).

All libVLC audio players share one Instance (created with --no-video):
creating an Instance scans the plugin cache and is expensive on a Pi, so it
is built once and reused. QtMultimedia is imported lazily inside __init__
because importing it before QApplication exists aborts Qt on some platforms.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# python-vlc raises OSError (not ImportError) when the package is installed
# but the native libVLC library is missing – catch both, never crash the app.
try:
    import vlc as _vlc
except (ImportError, OSError) as _e:
    _vlc = None
    logger.warning(
        "python-vlc/libVLC nicht verfügbar (%s) – Szenen-Audio und MP3-Töne sind "
        "deaktiviert! Auf dem Pi installieren mit: sudo apt install -y vlc python3-vlc",
        _e,
    )

_vlc_instance = None


def _get_vlc_instance():
    """Lazy shared libVLC instance for all audio playback (or None)."""
    global _vlc_instance
    if _vlc is None:
        return None
    if _vlc_instance is None:
        try:
            _vlc_instance = _vlc.Instance(["--quiet", "--no-video"])
        except Exception as e:
            logger.error("libVLC instance could not be created: %s", e)
    return _vlc_instance


class AudioPlayer:
    """One background music track + unlimited short one-shot sound effects."""

    def __init__(self, config=None):
        self._music_player = None        # vlc.MediaPlayer for current music
        self._vlc_sfx: list = []         # running one-shot VLC players
        self._aplay_procs: list = []     # running aplay subprocesses
        self._aplay_missing = False
        self._qt_effects: list = []      # keep QSoundEffect refs alive

        force_jack = True if config is None else bool(
            config.settings.get("force_headphone_audio", True))
        if sys.platform.startswith("linux") and force_jack:
            self._init_audio_routing()

        # Deferred import – must happen after QApplication is constructed.
        try:
            from PyQt6.QtCore import QUrl as _QUrl
            from PyQt6.QtMultimedia import QSoundEffect as _QSE
            self._QSoundEffect = _QSE
            self._QUrl = _QUrl
        except (ImportError, RuntimeError) as e:
            self._QSoundEffect = None
            self._QUrl = None
            logger.info("QSoundEffect not available (%s)", e)

    @property
    def music_available(self) -> bool:
        """True if the VLC backend for scene music is usable."""
        return _get_vlc_instance() is not None

    # ------------------------------------------------------------------
    # Audio routing init (Raspberry Pi)
    # ------------------------------------------------------------------

    @staticmethod
    def _init_audio_routing():
        """Route audio to the 3.5 mm headphone jack on Raspberry Pi.

        Tries two approaches (failures are logged, not fatal):
        1. pactl – find the headphone/bcm2835 PulseAudio/PipeWire sink and set
           it as default, so VLC, aplay and all other apps use it.
        2. amixer – force the legacy ALSA PCM route to analog (numid=3 = 1).
        Disable via settings.json: "force_headphone_audio": false.
        """
        try:
            r = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if r.returncode != 0:
                logger.warning("pactl failed (rc=%s): %s", r.returncode, r.stderr.strip())
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and any(
                        k in parts[1].lower() for k in ("headphone", "bcm2835")):
                    subprocess.run(
                        ["pactl", "set-default-sink", parts[1]],
                        capture_output=True, timeout=3, check=False,
                    )
                    logger.info("Default audio sink set to: %s", parts[1])
                    break
            else:
                logger.info("No headphone sink found in pactl output: %s",
                            r.stdout.strip() or "(empty)")
        except Exception as e:
            logger.warning("pactl not available: %s", e)
        try:
            subprocess.run(
                ["amixer", "cset", "numid=3", "1"],   # 1 = analog / headphone
                capture_output=True, timeout=2, check=False,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Music (single long track) – VLC
    # ------------------------------------------------------------------

    def play_music(self, path, loops: int = 0):
        """Play background music. loops=-1 → loop forever."""
        p = Path(path)
        if not p.exists():
            logger.warning("Audio file not found: %s", p)
            return
        inst = _get_vlc_instance()
        if inst is None:
            logger.warning("Cannot play music %s – VLC backend unavailable", p)
            return
        try:
            self.stop_music()
            media = inst.media_new(str(p))
            if loops != 0:
                # -1 means loop forever; otherwise repeat `loops` extra times.
                media.add_option(f"input-repeat={65535 if loops < 0 else loops}")
            self._music_player = inst.media_player_new()
            self._music_player.set_media(media)
            media.release()
            self._music_player.audio_set_volume(100)
            if self._music_player.play() == -1:
                logger.warning("VLC refused to play music: %s", p)
            else:
                logger.info("Music playing: %s", p.name)
        except Exception as e:
            logger.warning("Could not play music %s: %s", p, e)

    def stop_music(self):
        if self._music_player is not None:
            try:
                self._music_player.stop()
                self._music_player.release()
            except Exception:
                pass
            self._music_player = None

    def music_busy(self) -> bool:
        if self._music_player is None:
            return False
        try:
            return self._music_player.is_playing() == 1
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Sound effects (short one-shot)
    # ------------------------------------------------------------------

    def play_sfx(self, path):
        """Play a short sound effect. Effects may overlap (one player each).

        VLC first for every format: it uses the same PipeWire/PulseAudio
        route as the scene audio, while aplay opens ALSA directly and fails
        with "Device or resource busy" when the sound server owns the card.
        """
        p = Path(path)
        if not p.exists():
            logger.warning("SFX file not found: %s", p)
            return
        self._reap_finished()

        is_wav = p.suffix.lower() == ".wav"
        if self._play_sfx_vlc(p):
            return
        if is_wav and sys.platform.startswith("linux") and not self._aplay_missing:
            if self._play_sfx_aplay(p):
                return
        if is_wav and self._play_sfx_qt(p):
            return
        logger.warning("No audio backend could play SFX: %s", p)

    def _play_sfx_aplay(self, p: Path) -> bool:
        try:
            proc = subprocess.Popen(
                ["aplay", "-q", str(p)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._aplay_procs.append(proc)
            return True
        except (FileNotFoundError, OSError) as e:
            self._aplay_missing = True
            logger.warning("aplay not available (%s) – falling back to VLC", e)
            return False

    def _play_sfx_vlc(self, p: Path) -> bool:
        inst = _get_vlc_instance()
        if inst is None:
            return False
        try:
            player = inst.media_player_new()
            media = inst.media_new(str(p))
            player.set_media(media)
            media.release()
            player.audio_set_volume(100)
            if player.play() == -1:
                player.release()
                logger.warning("VLC refused to play SFX: %s", p)
                return False
            self._vlc_sfx.append(player)
            return True
        except Exception as e:
            logger.warning("VLC SFX failed for %s: %s", p, e)
            return False

    def _play_sfx_qt(self, p: Path) -> bool:
        if self._QSoundEffect is None:
            return False
        try:
            effect = self._QSoundEffect()
            effect.setSource(self._QUrl.fromLocalFile(str(p)))
            effect.play()
            self._qt_effects.append(effect)
            return True
        except Exception as e:
            logger.warning("QSoundEffect failed: %s", e)
            return False

    def _reap_finished(self):
        """Collect finished SFX backends; log aplay errors instead of hiding them."""
        still_running = []
        for proc in self._aplay_procs:
            rc = proc.poll()
            if rc is None:
                still_running.append(proc)
                continue
            if rc != 0 and proc.stderr is not None:
                err = proc.stderr.read().decode(errors="replace").strip()
                logger.warning("aplay failed (rc=%s): %s", rc, err or "(no output)")
                if "busy" in err.lower():
                    # The sound server owns the ALSA device; aplay will keep
                    # failing, so stop trying and use the other backends.
                    self._aplay_missing = True
            if proc.stderr is not None:
                proc.stderr.close()
        self._aplay_procs = still_running

        if _vlc is not None:
            ended = (_vlc.State.Ended, _vlc.State.Error, _vlc.State.Stopped)
            active = []
            for player in self._vlc_sfx:
                try:
                    if player.get_state() in ended:
                        player.release()
                    else:
                        active.append(player)
                except Exception:
                    pass
            self._vlc_sfx = active

        self._qt_effects = [e for e in self._qt_effects if e.isPlaying()]

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def stop_all(self):
        self.stop_music()
        for player in self._vlc_sfx:
            try:
                player.stop()
                player.release()
            except Exception:
                pass
        self._vlc_sfx.clear()
        for effect in self._qt_effects:
            try:
                effect.stop()
            except Exception:
                pass
        self._qt_effects.clear()
        self._reap_finished()

    # ------------------------------------------------------------------
    # Media duration probing (used by the admin scene editor)
    # ------------------------------------------------------------------

    @staticmethod
    def get_audio_duration(path) -> float | None:
        """Audio duration in seconds via mutagen, or None on failure."""
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(str(path))
            if audio is not None and audio.info is not None:
                return float(audio.info.length)
        except Exception as e:
            logger.warning("Cannot read duration of %s: %s", path, e)
        return None

    @staticmethod
    def get_video_duration(path) -> float | None:
        """Video duration in seconds (mutagen for MP4/MOV, libVLC for the rest)."""
        try:
            from mutagen import File as MutagenFile
            video = MutagenFile(str(path))
            if video is not None and video.info is not None and video.info.length:
                return float(video.info.length)
        except Exception as e:
            logger.debug("mutagen cannot read %s: %s", path, e)

        inst = _get_vlc_instance()
        if inst is not None:
            try:
                media = inst.media_new(str(path))
                media.parse_with_options(_vlc.MediaParseFlag.local, 3000)
                duration = None
                for _ in range(30):
                    dur = media.get_duration()
                    if dur > 0:
                        duration = dur / 1000.0
                        break
                    time.sleep(0.05)
                media.release()
                return duration
            except Exception as e:
                logger.warning("Cannot read video duration of %s (vlc): %s", path, e)
        return None
