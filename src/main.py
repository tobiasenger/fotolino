"""
Fotobox – entry point.

Usage:
    python src/main.py            # production (fullscreen kiosk)
    python src/main.py --dev      # dev mode: windowed + keyboard buttons (SPACE/F1)
                                  # + mock camera/GPIO/printer fallbacks
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Ensure project root is importable (so `python src/main.py` works)
sys.path.insert(0, str(Path(__file__).parent.parent))

_PYQT_INSTALL_HELP = """
ERROR: PyQt6 ist nicht installiert.

Auf dem Raspberry Pi (Bookworm):
  sudo apt update
  sudo apt install -y python3-pyqt6 python3-pyqt6.qtmultimedia

Auf dem Mac (Entwicklung):
  pip3 install -r requirements.txt
"""


def _configure_logging():
    from src.config_manager import BASE_DIR
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(BASE_DIR / "fotobox.log", maxBytes=1_000_000,
                                backupCount=3, encoding="utf-8"),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Fotobox")
    parser.add_argument("--dev", action="store_true",
                        help="Development mode: windowed, keyboard buttons, mock camera")
    args = parser.parse_args()

    _configure_logging()

    try:
        from PyQt6.QtWidgets import QApplication
    except ModuleNotFoundError:
        print(_PYQT_INSTALL_HELP, file=sys.stderr)
        sys.exit(1)

    from src.app import FotoboxApp
    from src.ui.theme import make_app_palette

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(make_app_palette())

    window = FotoboxApp(dev_mode=args.dev)  # noqa: F841 – must stay referenced
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
