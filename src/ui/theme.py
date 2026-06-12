"""
Central Qt theme: the application palette, shared stylesheet snippets for the
kiosk screens, and the loader for the swappable admin design file.

Admin design (CSS-like): the whole admin area is styled by ONE Qt stylesheet
(QSS) loaded from assets/themes/. Swap the file (or point the settings key
"admin_theme" to another file in that folder) to change the look without
touching any Python code. The selector contract the file must follow is
documented in ADMIN_DESIGN.md.
"""
from __future__ import annotations

import logging

from PyQt6.QtGui import QColor, QPalette

from ..config_manager import BASE_DIR

logger = logging.getLogger(__name__)

ACCENT = "#ff6600"

# ---------------------------------------------------------------------------
# Kiosk screens (non-admin)
# ---------------------------------------------------------------------------

LARGE_BTN_STYLE = (
    "QPushButton { background: #2a2a50; color: white; border: 2px solid #444488; "
    "border-radius: 6px; padding: 10px 20px; font-size: 20px; } "
    f"QPushButton:hover {{ border-color: {ACCENT}; }}"
)


def progress_bar_style(color: str) -> str:
    # Borderless: the bar is only a few pixels tall (constants.PROGRESS_BAR_H).
    return (
        "QProgressBar { border: none; background: #282828; } "
        f"QProgressBar::chunk {{ background: {color}; }}"
    )


def make_app_palette() -> QPalette:
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
    return palette


# ---------------------------------------------------------------------------
# Admin design file (swappable, CSS-like)
# ---------------------------------------------------------------------------

THEMES_DIR = BASE_DIR / "assets" / "themes"
DEFAULT_ADMIN_THEME = "admin_dark.qss"


def admin_stylesheet(config=None) -> str:
    """Return the QSS for the admin area.

    The file name is read from the settings key "admin_theme" (default:
    admin_dark.qss) and resolved inside assets/themes/. If the file cannot
    be read, a built-in minimal fallback keeps the admin fully usable.
    """
    name = DEFAULT_ADMIN_THEME
    if config is not None:
        name = str(config.settings.get("admin_theme", name) or name)
    path = THEMES_DIR / name
    try:
        qss = path.read_text(encoding="utf-8")
        logger.debug("Admin-Design geladen: %s", path)
        return qss
    except OSError:
        logger.warning("Admin-Design '%s' nicht lesbar – eingebautes "
                       "Standard-Design wird verwendet. Datei in assets/themes/ "
                       "und Einstellung 'admin_theme' prüfen.", path)
        return _ADMIN_FALLBACK_QSS


# Minimal functional dark style; only used when the theme file is missing.
_ADMIN_FALLBACK_QSS = f"""
#AdminRoot {{ background: #101018; }}
#AdminSidebar {{ background: #1e1e3a; }}
QLabel {{ color: white; }}
QLabel[kind="hint"], QLabel[kind="subtitle"] {{ color: #9999aa; }}
QLabel[kind="warn"] {{ color: #ff6060; }}
QLabel[kind="section"], QLabel[kind="title"], QLabel[kind="appname"] {{
    color: {ACCENT}; font-weight: bold; }}
QFrame[kind="separator"] {{ background: #333355; }}
QPushButton {{ background: #2a2a50; color: white; border: 1px solid #444488;
    border-radius: 5px; padding: 8px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:checked {{ background: {ACCENT}; }}
QPushButton[kind="danger"] {{ background: #5a2030; border-color: #884444; }}
QLineEdit, QComboBox, QListWidget {{ background: #141423; color: white;
    border: 1px solid #444488; border-radius: 5px; padding: 6px; }}
QScrollArea {{ border: none; background: transparent; }}
"""
