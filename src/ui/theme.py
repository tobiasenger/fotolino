"""
Central Qt theme: the application palette and all shared stylesheet snippets.
Change colors here instead of hunting through individual screens.
"""
from PyQt6.QtGui import QColor, QPalette

ACCENT = "#ff6600"

BTN_STYLE = (
    "QPushButton { background: #2a2a50; color: white; border: 1px solid #444488; "
    "border-radius: 5px; padding: 8px 14px; } "
    f"QPushButton:hover {{ border-color: {ACCENT}; }}"
)

LARGE_BTN_STYLE = (
    "QPushButton { background: #2a2a50; color: white; border: 2px solid #444488; "
    "border-radius: 6px; padding: 10px 20px; font-size: 20px; } "
    f"QPushButton:hover {{ border-color: {ACCENT}; }}"
)

DEL_BTN_STYLE = (
    "QPushButton { background: #5a2030; color: white; border: 1px solid #884444; "
    "border-radius: 5px; padding: 8px 14px; } "
    f"QPushButton:hover {{ border-color: {ACCENT}; }}"
)

# Checkable sidebar tab (left-aligned text)
TAB_BTN_STYLE = (
    "QPushButton { background: #2a2a50; color: white; border: none; "
    "border-radius: 6px; padding: 12px; font-size: 18px; text-align: left; } "
    "QPushButton:hover { background: #3a3a70; } "
    f"QPushButton:checked {{ background: {ACCENT}; }}"
)

# Checkable pill button (centered text, e.g. scene-type switcher)
PILL_BTN_STYLE = (
    "QPushButton { background: #2a2a50; color: white; border: none; "
    "border-radius: 5px; padding: 8px; } "
    f"QPushButton:checked {{ background: {ACCENT}; }}"
)

CLOSE_BTN_STYLE = (
    "QPushButton { background: #44224a; color: white; border: none; "
    "border-radius: 6px; padding: 12px; font-size: 18px; } "
    "QPushButton:hover { background: #663366; }"
)

SIDEBAR_STYLE = "background: #1e1e3a;"

WARN_LABEL_STYLE = "color: #ff6060;"


def progress_bar_style(color: str) -> str:
    return (
        "QProgressBar { border: 2px solid #333; border-radius: 5px; "
        "background: #282828; height: 24px; } "
        f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
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
