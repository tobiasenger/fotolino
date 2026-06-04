import logging
from pathlib import Path

import pygame

logger = logging.getLogger(__name__)

_MIXER_READY = False


def _ensure_mixer():
    global _MIXER_READY
    if not _MIXER_READY:
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            _MIXER_READY = True
        except pygame.error as e:
            logger.warning("pygame.mixer init failed: %s", e)


class AudioPlayer:
    """Plays MP3/WAV files. Supports one background music track + unlimited sound effects."""

    def __init__(self):
        _ensure_mixer()
        self._sfx_channel: pygame.mixer.Channel | None = None

    # ------------------------------------------------------------------
    # Music (single long track)
    # ------------------------------------------------------------------

    def play_music(self, path: str | Path, loops: int = 0, fade_ms: int = 0):
        if not _MIXER_READY:
            return
        p = Path(path)
        if not p.exists():
            logger.warning("Audio file not found: %s", p)
            return
        try:
            pygame.mixer.music.load(str(p))
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
        except pygame.error as e:
            logger.warning("Could not play music %s: %s", p, e)

    def stop_music(self, fade_ms: int = 0):
        if not _MIXER_READY:
            return
        if fade_ms:
            pygame.mixer.music.fadeout(fade_ms)
        else:
            pygame.mixer.music.stop()

    def music_busy(self) -> bool:
        return _MIXER_READY and pygame.mixer.music.get_busy()

    # ------------------------------------------------------------------
    # Sound effects (short one-shot)
    # ------------------------------------------------------------------

    def play_sfx(self, path: str | Path):
        if not _MIXER_READY:
            return
        p = Path(path)
        if not p.exists():
            logger.warning("SFX file not found: %s", p)
            return
        try:
            sound = pygame.mixer.Sound(str(p))
            sound.play()
        except pygame.error as e:
            logger.warning("Could not play sfx %s: %s", p, e)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def stop_all(self):
        if not _MIXER_READY:
            return
        pygame.mixer.music.stop()
        pygame.mixer.stop()

    @staticmethod
    def get_mp3_duration(path: str | Path) -> float | None:
        """Return duration in seconds, or None on failure."""
        try:
            from mutagen.mp3 import MP3
            audio = MP3(str(path))
            return audio.info.length
        except Exception as e:
            logger.warning("Cannot read duration of %s: %s", path, e)
            return None

    @staticmethod
    def get_video_duration(path: str | Path) -> float | None:
        try:
            import cv2
            cap = cv2.VideoCapture(str(path))
            fps   = cap.get(cv2.CAP_PROP_FPS) or 30
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            return frames / fps if fps else None
        except Exception as e:
            logger.warning("Cannot read video duration of %s: %s", path, e)
            return None
