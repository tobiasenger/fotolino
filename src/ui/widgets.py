"""
Reusable UI building blocks shared by screens and admin views:
  * draw_shadow_text()  – painter helper for HUD text with a drop shadow
  * NotificationLabel   – floating auto-hiding notification (top-left corner)
  * FileSelectRow       – line edit + browse button + extension warning
  * open_file_dialog()  – native file picker returning the chosen path
  * make_hint() / make_separator() / add_form_section() – admin form helpers

Admin widgets carry a dynamic "kind" property instead of inline styles; the
swappable admin theme (assets/themes/*.qss) styles them via attribute
selectors, e.g.  QPushButton[kind="primary"]  (see ADMIN_DESIGN.md).
"""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ..config_manager import BASE_DIR
from ..constants import FONT_FAMILY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Admin form helpers (styled via the admin theme's "kind" selectors)
# ---------------------------------------------------------------------------

def set_kind(widget: QWidget, kind: str) -> QWidget:
    """Tag a widget for the admin stylesheet (QSS attribute selector)."""
    widget.setProperty("kind", kind)
    return widget


def make_hint(text: str) -> QLabel:
    """Muted, word-wrapped explanation text."""
    label = QLabel(text)
    label.setWordWrap(True)
    set_kind(label, "hint")
    return label


def make_separator() -> QFrame:
    """Thin horizontal line separating blocks inside a form."""
    line = QFrame()
    line.setFixedHeight(1)
    set_kind(line, "separator")
    return line


def add_form_section(form: QFormLayout, title: str, first: bool = False):
    """Add a visually separated section heading spanning both form columns."""
    if not first:
        form.addRow(make_separator())
    label = QLabel(title)
    set_kind(label, "section")
    form.addRow(label)


def draw_shadow_text(painter: QPainter, x: int, y: int, w: int, h: int,
                     text: str, size: int, color: tuple,
                     align=Qt.AlignmentFlag.AlignCenter, offset: int = 2):
    """Draw bold text with a black drop shadow (readable on any background)."""
    font = QFont(FONT_FAMILY, size)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(0, 0, 0))
    painter.drawText(x + offset, y + offset, w, h, align, text)
    painter.setPen(QColor(*color))
    painter.drawText(x, y, w, h, align, text)


def open_file_dialog(parent, initial_path, title="Datei auswählen", extensions=None):
    """Native file-open dialog. Returns the selected path string or None."""
    try:
        start = str(Path(initial_path)) if initial_path and Path(initial_path).exists() \
            else str(Path.home())
    except Exception:
        start = str(Path.home())

    if extensions:
        ext_str = " ".join(f"*{e}" for e in sorted(extensions))
        filter_str = f"Erlaubte Dateien ({ext_str});;Alle Dateien (*)"
    else:
        filter_str = "Alle Dateien (*)"

    path, _ = QFileDialog.getOpenFileName(parent, title, start, filter_str)
    return path if path else None


class NotificationLabel(QLabel):
    """Floating notification in the top-left corner of its parent; auto-hides."""

    _COLORS = {"error": "#dc3c3c", "warning": "#ffbe00", "info": "#50d264"}
    _LOG_LEVELS = {"error": logging.ERROR, "warning": logging.WARNING}

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, message: str, duration: float = 7.0, level: str = "info"):
        color = self._COLORS.get(level, "#dddddd")
        self.setStyleSheet(
            f"background: rgba(0,0,0,210); color: white; padding: 12px 20px; "
            f"border-left: 6px solid {color}; font-size: 20px; border-radius: 4px;"
        )
        self.setText(message)
        parent = self.parentWidget()
        self.setMaximumWidth(max(400, (parent.width() if parent else 440) - 40))
        self.adjustSize()
        self.move(20, 20)
        self.raise_()
        self.show()
        self._timer.start(int(duration * 1000))
        logger.log(self._LOG_LEVELS.get(level, logging.INFO), "[Meldung] %s", message)


class FileSelectRow(QWidget):
    """Line edit + "…" browse button + warning label for file settings.

    Selected files are stored relative to the project root when possible.
    A warning appears when the extension is not in `extensions`.
    """

    textChanged = pyqtSignal(str)

    def __init__(self, config, extensions: set, kind: str, value: str = "",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._config = config
        self._extensions = extensions
        self._kind = kind

        self._line = QLineEdit(str(value))
        browse = QPushButton("…")
        set_kind(browse, "tool")
        browse.clicked.connect(self._browse)

        self._warn = QLabel("")
        set_kind(self._warn, "warn")
        self._warn.setWordWrap(True)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._line, 1)
        row.addWidget(browse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
        layout.addWidget(self._warn)

        self._line.textChanged.connect(self._on_text_changed)
        self._validate()

    # ------------------------------------------------------------------

    def text(self) -> str:
        return self._line.text().strip()

    def setText(self, value: str):
        self._line.setText(str(value))

    def _on_text_changed(self, text: str):
        self._validate()
        self.textChanged.emit(text)

    def _browse(self):
        base = str(self._config.resolve_asset("assets"))
        sel = open_file_dialog(self, base, f"{self._kind} auswählen", self._extensions)
        if not sel:
            return
        try:
            rel = Path(sel).resolve().relative_to(BASE_DIR.resolve())
            self._line.setText(str(rel))
        except ValueError:
            self._line.setText(sel)

    def _validate(self):
        path = self.text()
        if path and Path(path).suffix.lower() not in self._extensions:
            allowed = ", ".join(sorted(self._extensions))
            self._warn.setText(
                f"Warnung: {self._kind} sollte eines dieser Formate sein: {allowed}")
            self._warn.show()
        else:
            self._warn.setText("")
