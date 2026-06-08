"""
Base class for all application screens (PyQt6).
Each screen is a QWidget added to the main QStackedWidget.
"""
from pathlib import Path

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


class BaseScreen(QWidget):
    """Abstract base for all application screens."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    # ------------------------------------------------------------------
    # Lifecycle hooks (override in subclasses)
    # ------------------------------------------------------------------

    def on_enter(self):
        pass

    def on_exit(self):
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def transition_to(self, screen_name: str):
        self.app.switch_screen(screen_name)

    def _load_pixmap(self, path: str) -> QPixmap | None:
        """Load an image (resolved relative to project root) as a QPixmap."""
        if not path:
            return None
        p = self.app.config.resolve_asset(path)
        if not p.exists():
            return None
        pix = QPixmap(str(p))
        return pix if not pix.isNull() else None

    @staticmethod
    def _scaled_cover(pixmap: QPixmap, w: int, h: int) -> QPixmap:
        """Scale a pixmap to cover a w×h area (KeepAspectRatioByExpanding)."""
        return pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
