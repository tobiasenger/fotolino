"""
Fotobox – main entry point (PyQt6).

Usage:
    python src/main.py            # production (fullscreen)
    python src/main.py --dev      # dev mode: windowed + keyboard GPIO fallback + mock camera
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QLabel
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
except ModuleNotFoundError:
    print(
        "\n"
        "ERROR: PyQt6 ist nicht installiert.\n"
        "\n"
        "Auf dem Raspberry Pi (Bookworm):\n"
        "  sudo apt update\n"
        "  sudo apt install -y python3-pyqt6 python3-pyqt6.qtmultimedia\n"
        "\n"
        "Auf dem Mac (Entwicklung):\n"
        "  pip3 install -r requirements.txt\n",
        file=sys.stderr,
    )
    sys.exit(1)
from PyQt6.QtGui import QPalette, QColor

from src.constants     import SCREEN_W, SCREEN_H
from src.config_manager import ConfigManager
from src.state          import AppContext, AppState
from src.gpio_handler   import GPIOHandler
from src.audio          import AudioPlayer
from src.camera         import CameraController
from src.storage        import StorageManager
from src.collage        import CollageCreator
from src.printer        import Printer

from src.ui.screen_start       import StartScreen
from src.ui.screen_intro       import IntroScreen
from src.ui.screen_capture     import CaptureScreen
from src.ui.screen_collage     import CollageScreen
from src.ui.screen_print       import PrintScreen
from src.ui.screen_camera_test import CameraTestScreen
from src.ui.admin.admin_main   import AdminMain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("fotobox.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fotobox.main")


class FotoboxApp(QMainWindow):
    _gpio_button = pyqtSignal(str)
    # message, duration (s), level — used so notifications can be raised from any thread.
    _notify_sig = pyqtSignal(str, float, str)

    def __init__(self, dev_mode: bool = False):
        super().__init__()
        self.dev_mode = dev_mode
        self.setWindowTitle("Fotobox")

        # Services
        self.config = ConfigManager()
        self.context = AppContext()
        self.audio = AudioPlayer()
        self.camera = CameraController(
            self.config.settings.get("screen_width", SCREEN_W),
            self.config.settings.get("screen_height", SCREEN_H),
        )
        self.storage = StorageManager(self.config)
        self.collage_creator = CollageCreator(self.config)
        self.printer = Printer(self.config)

        # GPIO (signal fires from non-main thread → auto-queued to main thread)
        self._gpio_button.connect(self._handle_button)
        self.gpio = GPIOHandler(self.config, self._gpio_button.emit)

        # Notifications (queued so background threads can use show_notification safely)
        self._notify_sig.connect(self._show_notification_main)

        # UI stack
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        self.screens = {
            "start":       StartScreen(self),
            "intro":       IntroScreen(self),
            "capture":     CaptureScreen(self),
            "collage":     CollageScreen(self),
            "print":       PrintScreen(self),
            "camera_test": CameraTestScreen(self),
            "admin":       AdminMain(self),
        }
        for scr in self.screens.values():
            self.stack.addWidget(scr)

        # Notification overlay (floating QLabel above the stack)
        self._notif_label = QLabel(self)
        self._notif_label.setWordWrap(True)
        self._notif_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._notif_label.hide()
        self._notif_timer = QTimer(self)
        self._notif_timer.setSingleShot(True)
        self._notif_timer.timeout.connect(self._notif_label.hide)

        if dev_mode:
            self.resize(1280, 720)
            self.show()
        else:
            self.showFullScreen()
            self.setCursor(Qt.CursorShape.BlankCursor)

        self._current_name = ""
        self.switch_screen("start")
        logger.info("Fotobox started (dev=%s)", dev_mode)

    # ------------------------------------------------------------------

    def switch_screen(self, name: str):
        if name not in self.screens:
            logger.warning("Unknown screen: %s", name)
            return
        old = self.screens.get(self._current_name)
        if old:
            old.on_exit()
        self._current_name = name
        self.stack.setCurrentWidget(self.screens[name])

        state_map = {
            "start": AppState.READY, "intro": AppState.INTRO,
            "capture": AppState.CAPTURE, "collage": AppState.COLLAGE,
            "print": AppState.PRINT, "camera_test": AppState.ADMIN,
            "admin": AppState.ADMIN,
        }
        if name in state_map and self.context.state != AppState.ADMIN:
            self.context.state = state_map[name]
        self.screens[name].on_enter()
        logger.info("Screen → %s", name)

    # ------------------------------------------------------------------

    def show_notification(self, message: str, duration: float = 7.0, level: str = "info"):
        """Thread-safe: routes through a queued signal to the GUI thread."""
        self._notify_sig.emit(message, duration, level)

    @pyqtSlot(str, float, str)
    def _show_notification_main(self, message: str, duration: float, level: str):
        colors = {"error": "#dc3c3c", "warning": "#ffbe00", "info": "#50d264"}
        color = colors.get(level, "#dddddd")
        self._notif_label.setStyleSheet(
            f"background: rgba(0,0,0,210); color: white; padding: 12px 20px; "
            f"border-left: 6px solid {color}; font-size: 20px; border-radius: 4px;"
        )
        self._notif_label.setText(message)
        self._notif_label.setMaximumWidth(max(400, self.width() - 40))
        self._notif_label.adjustSize()
        self._notif_label.move(20, 20)
        self._notif_label.raise_()
        self._notif_label.show()
        self._notif_timer.start(int(duration * 1000))
        lvl = {"error": logging.ERROR, "warning": logging.WARNING}.get(level, logging.INFO)
        logger.log(lvl, "[Notification] %s", message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._notif_label.move(20, 20)

    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _handle_button(self, action: str):
        if action == "start_button":
            if self.context.state == AppState.READY:
                path = self.config.select_random_path()
                if not path:
                    self.show_notification(
                        "Keine Pfade konfiguriert – Admin-Taste drücken",
                        duration=6.0, level="warning")
                    return
                scenes_cfg = path.get("scenes", {})
                path_name = path.get("name", "?")
                if not scenes_cfg.get("greeting"):
                    self.show_notification(
                        f"Pfad '{path_name}' hat keine Begrüßungsszene.",
                        duration=8.0, level="error")
                    return
                cap_count = scenes_cfg.get("capture_count", 0)
                if cap_count > 0 and not scenes_cfg.get("collage"):
                    self.show_notification(
                        f"Pfad '{path_name}' hat keine Collage-Szene.",
                        duration=8.0, level="error")
                    return
                if cap_count > 0 and not scenes_cfg.get("print"):
                    self.show_notification(
                        f"Pfad '{path_name}' hat keine Druck-Szene.",
                        duration=8.0, level="error")
                    return
                if cap_count > 0 and not self.storage.usb_available():
                    self.show_notification("USB-Stick nicht gefunden", level="warning")
                self.context.start_path(path)
                self.switch_screen("intro")

        elif action == "admin_button":
            if self.context.state == AppState.ADMIN:
                self.context.exit_admin()
                self.switch_screen("start")
            elif self.context.state in (AppState.READY, AppState.INTRO):
                self.context.enter_admin()
                self.switch_screen("admin")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
        elif event.key() == Qt.Key.Key_Space:
            self._gpio_button.emit("start_button")
        elif event.key() == Qt.Key.Key_F1:
            self._gpio_button.emit("admin_button")
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        logger.info("Shutting down…")
        old = self.screens.get(self._current_name)
        if old:
            try:
                old.on_exit()
            except Exception:
                pass
        self.gpio.cleanup()
        self.camera.cleanup()
        self.audio.stop_all()
        event.accept()


# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fotobox")
    parser.add_argument("--dev", action="store_true",
                        help="Development mode: windowed, keyboard buttons, mock camera")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(10, 10, 20))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(20, 20, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(30, 30, 50))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(42, 42, 80))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(255, 102, 0))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = FotoboxApp(dev_mode=args.dev)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
