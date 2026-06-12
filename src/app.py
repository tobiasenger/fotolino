"""
Main application window: owns all services and the screen stack.

To add a new screen, add one entry to _SCREEN_DEFS – name, class and the
AppState the application is in while the screen is active.
"""
from __future__ import annotations

import logging
import threading

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from src.audio import AudioPlayer
from src.camera import CameraController
from src.collage import CollageCreator
from src.config_manager import ConfigManager
from src.constants import MAX_PATH_SEGMENTS, SCREEN_H, SCREEN_W
from src.gpio_handler import GPIOHandler
from src.printer import Printer
from src.state import AppContext, AppState
from src.storage import StorageManager
from src.ui.admin.admin_main import AdminMain
from src.ui.screen_camera_test import CameraTestScreen
from src.ui.screen_capture import CaptureScreen
from src.ui.screen_collage import CollageScreen
from src.ui.screen_gallery import (
    GalleryBrowseScreen, GalleryMenuScreen, GalleryPrintScreen,
)
from src.ui.screen_intro import IntroScreen
from src.ui.screen_print import PrintScreen
from src.ui.screen_segment import SegmentScreen
from src.ui.screen_start import StartScreen
from src.ui.widgets import NotificationLabel

logger = logging.getLogger(__name__)

#: (name, screen class, app state while the screen is active)
_SCREEN_DEFS = (
    ("start", StartScreen, AppState.READY),
    ("intro", IntroScreen, AppState.INTRO),
    ("capture", CaptureScreen, AppState.CAPTURE),
    ("collage", CollageScreen, AppState.COLLAGE),
    ("print", PrintScreen, AppState.PRINT),
    ("segment", SegmentScreen, AppState.SEGMENT),
    ("gallery_menu", GalleryMenuScreen, AppState.GALLERY),
    ("gallery_browse", GalleryBrowseScreen, AppState.GALLERY),
    ("gallery_print", GalleryPrintScreen, AppState.GALLERY),
    ("camera_test", CameraTestScreen, AppState.ADMIN),
    ("admin", AdminMain, AppState.ADMIN),
)

#: Screens on which the mouse cursor stays visible (touch/maintenance UI)
_CURSOR_SCREENS = {"admin", "camera_test"}


class FotoboxApp(QMainWindow):
    # Queued signals so GPIO callbacks / worker threads safely reach the GUI thread.
    _gpio_button = pyqtSignal(str)
    _notify = pyqtSignal(str, float, str)
    _collage_built = pyqtSignal(object, bool)   # (saved path str | None, error)

    def __init__(self, dev_mode: bool = False):
        super().__init__()
        self.dev_mode = dev_mode
        self.setWindowTitle("Fotobox")

        self._init_services()
        self._init_ui()

        self._current_name = ""
        self.switch_screen("start")

        if not self.audio.music_available:
            self.show_notification(
                "Audio-Backend (python-vlc) fehlt – Szenen-Audio bleibt stumm. "
                "Siehe FIX_AUDIO.md.", duration=12.0, level="warning")
        logger.info("Fotobox gestartet (Dev-Modus=%s)", dev_mode)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _init_services(self):
        self.config = ConfigManager()
        self.context = AppContext()
        self.audio = AudioPlayer(self.config)
        self.camera = CameraController(
            self.config.settings.get("screen_width", SCREEN_W),
            self.config.settings.get("screen_height", SCREEN_H),
        )
        self.storage = StorageManager(self.config)
        self.collage_creator = CollageCreator(self.config)
        self.printer = Printer(self.config)

        # GPIO fires from its own thread → queued signal hops to the GUI thread.
        self._gpio_button.connect(self._handle_button)
        self.gpio = GPIOHandler(self.config, self._gpio_button.emit)

        self._notify.connect(self._show_notification)
        self._collage_built.connect(self._on_collage_built)

    def _init_ui(self):
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        self.screens = {}
        self._screen_states = {}
        for name, screen_cls, state in _SCREEN_DEFS:
            screen = screen_cls(self)
            self.screens[name] = screen
            self._screen_states[name] = state
            self.stack.addWidget(screen)

        self._notif = NotificationLabel(self)

        if self.dev_mode or not self.config.settings.get("fullscreen", True):
            self.resize(1280, 720)
            self.show()
        else:
            self.showFullScreen()
            self.setCursor(Qt.CursorShape.BlankCursor)

    # ------------------------------------------------------------------
    # Screen switching
    # ------------------------------------------------------------------

    def switch_screen(self, name: str):
        if name not in self.screens:
            logger.warning("Unbekannter Screen angefordert: '%s' – Wechsel ignoriert", name)
            return
        old = self.screens.get(self._current_name)
        if old:
            old.on_exit()
        self._current_name = name
        self.stack.setCurrentWidget(self.screens[name])

        if self.context.state != AppState.ADMIN:
            self.context.state = self._screen_states[name]

        # Cursor: visible on admin screens, hidden in kiosk flow
        if not self.dev_mode:
            visible = name in _CURSOR_SCREENS
            self.setCursor(Qt.CursorShape.ArrowCursor if visible
                           else Qt.CursorShape.BlankCursor)

        self.screens[name].on_enter()
        logger.info("Screen-Wechsel: %s", name)

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def show_notification(self, message: str, duration: float = 7.0, level: str = "info"):
        """Thread-safe: routes through a queued signal to the GUI thread."""
        self._notify.emit(message, duration, level)

    @pyqtSlot(str, float, str)
    def _show_notification(self, message: str, duration: float, level: str):
        self._notif.show_message(message, duration, level)

    # ------------------------------------------------------------------
    # Button handling (GPIO or keyboard fallback)
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _handle_button(self, action: str):
        # The active screen gets first pick (gallery navigation etc.).
        current = self.screens.get(self._current_name)
        if current and current.handle_button(action):
            return
        if action == "start_button":
            if self.context.state == AppState.READY:
                self._start_session()
        elif action == "gallery_button":
            if (self.context.state == AppState.READY
                    and self.config.gallery_enabled()):
                self.switch_screen("gallery_menu")
        elif action == "admin_button":
            if self.context.state == AppState.ADMIN:
                self.context.exit_admin()
                self.switch_screen("start")
            elif self.context.state in (AppState.READY, AppState.INTRO):
                self.context.enter_admin()
                self.switch_screen("admin")

    def _start_session(self):
        path = self.config.select_random_path()
        if not path:
            self.show_notification(
                "Keine Pfade konfiguriert – Admin-Taste drücken",
                duration=6.0, level="warning")
            return
        error = self._path_config_error(path)
        if error:
            self.show_notification(error, duration=8.0, level="error")
            return
        if self._path_takes_photos(path) and not self.storage.usb_available():
            self.show_notification("USB-Stick nicht gefunden", level="warning")
        self.context.start_path(path)
        if self.context.is_custom_path():
            self._enter_segment()
        else:
            self.switch_screen("intro")

    @staticmethod
    def _path_takes_photos(path: dict) -> bool:
        """True if the path captures photos (and therefore needs the USB stick)."""
        if path.get("type") == "custom":
            return any(s.get("type") == "capture"
                       for s in path.get("segments", []))
        return path.get("scenes", {}).get("capture_count", 0) > 0

    @staticmethod
    def _path_config_error(path: dict) -> str | None:
        """Validate that the chosen path references everything it needs."""
        name = path.get("name", "?")
        if path.get("type") == "custom":
            return FotoboxApp._custom_path_error(name, path.get("segments", []))
        scenes = path.get("scenes", {})
        if not scenes.get("greeting"):
            return f"Pfad '{name}' hat keine Begrüßungsszene."
        if scenes.get("capture_count", 0) > 0:
            if not scenes.get("collage"):
                return f"Pfad '{name}' hat keine Collage-Szene."
            if not scenes.get("print"):
                return f"Pfad '{name}' hat keine Druck-Szene."
        return None

    @staticmethod
    def _custom_path_error(name: str, segments: list) -> str | None:
        if not segments:
            return f"Pfad '{name}' hat keine Segmente."
        if len(segments) > MAX_PATH_SEGMENTS:
            return f"Pfad '{name}' hat mehr als {MAX_PATH_SEGMENTS} Segmente."
        for i, seg in enumerate(segments, start=1):
            stype = seg.get("type")
            if stype not in ("image", "gif", "camera", "capture", "print"):
                return f"Pfad '{name}': Segment {i} hat einen unbekannten Typ."
            if stype == "image" and not seg.get("image"):
                return f"Pfad '{name}': Segment {i} (Bild) hat keine Bilddatei."
            if stype == "gif" and not seg.get("gif"):
                return f"Pfad '{name}': Segment {i} (GIF) hat keine GIF-Datei."
            if stype == "capture":
                try:
                    count = int(seg.get("capture_count", 0))
                except (TypeError, ValueError):
                    count = 0
                if not 1 <= count <= 4:
                    return (f"Pfad '{name}': Segment {i} (Aufnahme) hat keine "
                            f"gültige Fotoanzahl (1–4).")
        return None

    # ------------------------------------------------------------------
    # Custom path flow (segment sequence)
    # ------------------------------------------------------------------

    def _enter_segment(self):
        """Show the screen for the current segment of a running custom path."""
        segment = self.context.current_segment()
        if segment is None:   # defensive – paths are validated before start
            self.context.end_session()
            self.switch_screen("start")
            return
        self.switch_screen(
            "capture" if segment.get("type") == "capture" else "segment")

    def advance_segment(self):
        """Called by the capture/segment screens when their segment is done."""
        ctx = self.context
        ctx.segment_index += 1
        if ctx.segment_index < len(ctx.segments()):
            self._enter_segment()
        else:
            ctx.end_session()
            self.switch_screen("start")

    def start_collage_build(self):
        """Build and save the collage of a finished capture segment in the
        background. A later print segment waits via context.collage_pending."""
        photos = list(self.context.captured_photos)
        if not photos:
            return
        self.context.collage_pending = True

        def work():
            path, error = None, False
            try:
                image = self.collage_creator.create(photos, len(photos))
                path = str(self.storage.save_collage(image))
            except Exception:
                logger.exception("Collage-Erstellung fehlgeschlagen")
                error = True
            self._collage_built.emit(path, error)

        threading.Thread(target=work, daemon=True).start()

    @pyqtSlot(object, bool)
    def _on_collage_built(self, path, error: bool):
        self.context.collage_pending = False
        if path:
            self.context.collage_path = path
        elif error:
            self.show_notification(
                "Collage konnte nicht erstellt werden – Details in fotobox.log.",
                duration=8.0, level="error")

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
        elif event.key() == Qt.Key.Key_Space:
            self._gpio_button.emit("start_button")
        elif event.key() == Qt.Key.Key_F1:
            self._gpio_button.emit("admin_button")
        elif event.key() == Qt.Key.Key_L:
            self._gpio_button.emit("gallery_button")
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        logger.info("Fotobox wird beendet…")
        current = self.screens.get(self._current_name)
        if current:
            try:
                current.on_exit()
            except Exception:
                logger.exception("Fehler beim Verlassen des Screens '%s' "
                                 "während des Beendens", self._current_name)
        self.gpio.cleanup()
        self.camera.cleanup()
        self.audio.stop_all()
        event.accept()
