"""
Audio playback for the Fotobox.

Two-tier design:
  * System sound effects (shutter click) → QSoundEffect. WAV only.
  * Background music (scene audio)        → VLC MediaPlayer. WAV / MP3 / OGG.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import vlc as _vlc
    _VLC = True
except ImportError:
    _VLC = False
    logger.info("python-vlc not available – background music disabled")


class AudioPlayer:
    """One background music track (VLC) + unlimited short WAV sound effects (Qt).

    QSoundEffect (and the entire QtMultimedia backend) is imported lazily inside
    __init__ so it is only loaded after QApplication exists.  Importing
    PyQt6.QtMultimedia at module level causes a Qt abort on some platforms.
    """

    def __init__(self):
        self._instance = _vlc.Instance("--no-video") if _VLC else None
        self._music_player = None          # vlc.MediaPlayer for current music
        self._effects: list = []           # keep QSoundEffect refs alive

        # Deferred import – must happen after QApplication is constructed.
        try:
            from PyQt6.QtMultimedia import QSoundEffect as _QSE
            from PyQt6.QtCore import QUrl as _QUrl
            self._QSoundEffect = _QSE
            self._QUrl = _QUrl
            self._qt_sfx = True
        except (ImportError, RuntimeError) as e:
            self._QSoundEffect = None
            self._QUrl = None
            self._qt_sfx = False
            logger.info("QSoundEffect not available (%s) – system sounds disabled", e)

    # ------------------------------------------------------------------
    # Music (single long track) – VLC
    # ------------------------------------------------------------------

    def play_music(self, path, loops: int = 0):
        """Play background music. loops=-1 → loop forever (VLC input-repeat)."""
        if not self._instance:
            return
        p = Path(path)
        if not p.exists():
            logger.warning("Audio file not found: %s", p)
            return
        try:
            self.stop_music()
            media = self._instance.media_new(str(p))
            if loops != 0:
                # -1 means loop forever; otherwise repeat `loops` extra times.
                repeat = 65535 if loops < 0 else loops
                media.add_option(f"input-repeat={repeat}")
            self._music_player = self._instance.media_player_new()
            self._music_player.set_media(media)
            self._music_player.play()
        except Exception as e:
            logger.warning("Could not play music %s: %s", p, e)

    def stop_music(self):
        if self._music_player is not None:
            try:
                self._music_player.stop()
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
    # Sound effects (short one-shot) – WAV only
    # ------------------------------------------------------------------

    def play_sfx(self, path):
        import sys
        p = Path(path)
        if not p.exists():
            logger.warning("SFX file not found: %s", p)
            return
        if p.suffix.lower() != ".wav":
            logger.warning(
                "System sound '%s' is not a WAV file – only WAV is supported. "
                "Sound will not play.", p,
            )
            return

        # aplay is the most reliable WAV player on Pi/Linux – no Qt or VLC dependency.
        if sys.platform.startswith("linux"):
            try:
                import subprocess
                subprocess.Popen(
                    ["aplay", "-q", str(p)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except (FileNotFoundError, OSError) as e:
                logger.debug("aplay not available (%s) – trying QSoundEffect", e)

        # QSoundEffect fallback (Mac / Windows, or if aplay is missing).
        if self._qt_sfx:
            try:
                effect = self._QSoundEffect()
                effect.setSource(self._QUrl.fromLocalFile(str(p)))
                effect.play()
                self._effects.append(effect)
                self._effects = [e for e in self._effects if e.isPlaying() or e is effect]
                return
            except Exception as e:
                logger.warning("QSoundEffect failed: %s", e)

        logger.warning("No audio backend available for SFX: %s", p)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def stop_all(self):
        self.stop_music()
        for e in self._effects:
            try:
                e.stop()
            except Exception:
                pass
        self._effects.clear()

    @staticmethod
    def get_mp3_duration(path) -> float | None:
        """Return audio duration in seconds, or None on failure (uses mutagen)."""
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
        try:
            import cv2
            cap = cv2.VideoCapture(str(path))
            fps    = cap.get(cv2.CAP_PROP_FPS) or 30
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            if fps and frames:
                return frames / fps
        except Exception as e:
            logger.warning("Cannot read video duration of %s (cv2): %s", path, e)
        # Fallback to VLC media parsing if available
        if _VLC:
            try:
                inst = _vlc.Instance("--no-video")
                media = inst.media_new(str(path))
                media.parse_with_options(_vlc.MediaParseFlag.local, 3000)
                import time
                for _ in range(30):
                    dur = media.get_duration()
                    if dur > 0:
                        return dur / 1000.0
                    time.sleep(0.05)
            except Exception as e:
                logger.warning("Cannot read video duration of %s (vlc): %s", path, e)
        return None
