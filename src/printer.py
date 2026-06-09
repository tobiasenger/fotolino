from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

try:
    import cups
    _CUPS_AVAILABLE = True
except ImportError:
    _CUPS_AVAILABLE = False
    logger.info("pycups not available – printing will use mock output")

_DEMO_MSG = (
    "\n"
    "╔══════════════════════════════════════════════════════════╗\n"
    "║  DEMO-MODUS: Hier würde normalerweise ein Foto gedruckt  ║\n"
    "║  werden. Drucker wird nicht angesteuert.                 ║\n"
    "╚══════════════════════════════════════════════════════════╝"
)


class Printer:
    def __init__(self, config_manager):
        self._cfg          = config_manager
        self._printer_name = config_manager.settings.get("printer_name", "SELPHY")
        self._conn         = None
        self._connect()

    def _connect(self):
        if not _CUPS_AVAILABLE:
            return
        try:
            self._conn = cups.Connection()
            printers = self._conn.getPrinters()
            if self._printer_name not in printers:
                logger.warning(
                    "Drucker '%s' nicht in CUPS gefunden. "
                    "Verfügbare Drucker: %s. "
                    "Bitte Druckername in den Einstellungen prüfen oder Drucker verbinden.",
                    self._printer_name, list(printers.keys()) or ["(keine)"]
                )
        except Exception as e:
            logger.warning(
                "CUPS-Verbindung fehlgeschlagen: %s. "
                "Bitte sicherstellen, dass CUPS läuft (`systemctl status cups`) "
                "und der Drucker verbunden/erreichbar ist.",
                e
            )
            self._conn = None

    # ------------------------------------------------------------------

    def is_demo(self) -> bool:
        return self._cfg.settings.get("demo_mode", False)

    def print_collage(self, image_path: Path | str) -> bool:
        """Send a JPEG to the configured CUPS printer. Returns True on success."""
        if self.is_demo():
            print(_DEMO_MSG)
            logger.info("Demo-Modus aktiv: Druckvorgang übersprungen für %s", image_path)
            return True

        path = Path(image_path)
        if not path.exists():
            logger.error(
                "Druckfehler: Datei nicht gefunden: %s. "
                "Bitte prüfen, ob der USB-Stick korrekt eingehängt ist.",
                path
            )
            return False

        if not self._conn:
            self._connect()  # retry connection

        if self._conn:
            try:
                job_id = self._conn.printFile(
                    self._printer_name,
                    str(path),
                    "Fotobox",
                    {"fit-to-page": "true", "media": "w288h432"},
                )
                logger.info("Druckauftrag gesendet: Job-ID=%s, Datei=%s", job_id, path)
                return True
            except cups.IPPError as e:
                logger.error(
                    "Druckfehler (CUPS IPP %s): %s. "
                    "Bitte prüfen: Drucker eingeschaltet? Kabel/WLAN verbunden? "
                    "Papier eingelegt? CUPS-Status: `lpstat -p %s`",
                    e.args[0] if e.args else "?", e, self._printer_name
                )
                return False
            except Exception as e:
                logger.error(
                    "Druckfehler (unbekannt): %s. "
                    "CUPS-Log prüfen: `journalctl -u cups --since '5 minutes ago'`",
                    e
                )
                return False
        else:
            logger.error(
                "Drucker '%s' nicht erreichbar: CUPS-Verbindung nicht verfügbar. "
                "CUPS-Dienst prüfen: `sudo systemctl restart cups`",
                self._printer_name
            )
            return False

    def print_image(self, img: Image.Image) -> bool:
        """Save PIL image to a temp file and print it (CUPS copies it to its spool)."""
        if self.is_demo():
            print(_DEMO_MSG)
            return True
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                img.save(tmp, "JPEG", quality=95)
            return self.print_collage(tmp_path)
        except Exception as e:
            logger.error("print_image fehlgeschlagen: %s", e)
            return False
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def printer_ready(self) -> bool:
        if self.is_demo():
            return True
        if not self._conn:
            return False
        try:
            printers = self._conn.getPrinters()
            info  = printers.get(self._printer_name, {})
            state = info.get("printer-state", 0)
            return state in (3, 4)  # 3 = idle, 4 = processing
        except Exception:
            return False
