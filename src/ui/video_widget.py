"""
Embedded libVLC video surface.

One shared libVLC instance is used for all video playback in the app –
creating an Instance scans the plugin cache and is expensive on a Pi.
(Audio-only playback uses a separate --no-video instance, see src/audio.py;
sharing it here would break video output.)
"""
from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame

logger = logging.getLogger(__name__)

# python-vlc raises OSError (not ImportError) when the native libVLC is missing.
try:
    import vlc as _vlc
except (ImportError, OSError):
    _vlc = None

_vlc_instance = None


def _get_video_instance():
    global _vlc_instance
    if _vlc is None:
        return None
    if _vlc_instance is None:
        try:
            _vlc_instance = _vlc.Instance(["--quiet"])
        except Exception as e:
            logger.error("libVLC-Video-Instanz konnte nicht erstellt werden (%s) "
                         "– Video-Szenen werden ohne Video abgespielt.", e)
    return _vlc_instance


class VlcVideoFrame(QFrame):
    """QFrame that libVLC renders into. Caller controls geometry via setGeometry().

    play() returns False when no VLC backend is available so the caller can
    fall back immediately; asynchronous failures emit `playback_failed`.
    """

    playback_failed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: black;")
        self.hide()
        self._player = None

    def play(self, path, loop: bool = False, muted: bool = False) -> bool:
        self.stop()
        inst = _get_video_instance()
        if inst is None:
            logger.warning("Video %s kann nicht abgespielt werden – VLC-Backend "
                           "nicht verfügbar (siehe FIX_AUDIO.md).", path)
            return False
        try:
            media = inst.media_new(str(path))
            if loop:
                media.add_option("input-repeat=65535")
            self._player = inst.media_player_new()
            self._player.set_media(media)
            media.release()
            if muted:
                self._player.audio_set_mute(True)
            self.show()
            # The native window id is only usable once the frame is realised.
            QTimer.singleShot(200, self._attach_and_play)
            return True
        except Exception as e:
            logger.warning("Video-Wiedergabe von %s konnte nicht vorbereitet "
                           "werden: %s", path, e)
            self.stop()
            return False

    def _attach_and_play(self):
        if self._player is None:
            return
        try:
            wid = int(self.winId())
            if sys.platform.startswith("linux"):
                self._player.set_xwindow(wid)
            elif sys.platform == "darwin":
                self._player.set_nsobject(wid)
            elif sys.platform == "win32":
                self._player.set_hwnd(wid)
            if self._player.play() == -1:
                raise RuntimeError("libVLC refused to start playback")
        except Exception as e:
            logger.warning("Video-Wiedergabe fehlgeschlagen: %s – Szene fällt "
                           "auf Bild+Audio zurück.", e)
            self.stop()
            self.playback_failed.emit()

    def stop(self):
        if self._player is not None:
            try:
                self._player.stop()
                self._player.release()
            except Exception:
                pass
            self._player = None
        self.hide()
