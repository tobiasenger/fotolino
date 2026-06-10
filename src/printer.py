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
        self._target       = None  # tatsächlicher CUPS-Warteschlangenname
        self._connect()

    def _connect(self):
        if not _CUPS_AVAILABLE:
            return
        try:
            self._conn = cups.Connection()
        except Exception as e:
            logger.warning(
                "CUPS-Verbindung fehlgeschlagen: %s. "
                "Bitte sicherstellen, dass CUPS läuft (`systemctl status cups`) "
                "und der Drucker verbunden/erreichbar ist.",
                e
            )
            self._conn = None
            return
        self._refresh_target()

    def _refresh_target(self) -> str | None:
        """Resolve the configured printer name against the queues known to CUPS.

        Re-reads the name from the settings (admin screen can change it at
        runtime) and tolerates inexact names, e.g. a queue created via the
        CUPS web UI is usually called 'Canon_SELPHY_CP1500'.
        """
        if not self._conn:
            return None
        self._printer_name = self._cfg.settings.get("printer_name", "SELPHY")
        try:
            printers = self._conn.getPrinters()
        except Exception as e:
            logger.warning("CUPS-Abfrage fehlgeschlagen: %s", e)
            self._conn = None
            self._target = None
            return None

        resolved = self._resolve_name(printers)
        if resolved is None:
            logger.warning(
                "Drucker '%s' nicht in CUPS gefunden. Verfügbare Drucker: %s. "
                "Der Drucker muss einmalig als CUPS-Warteschlange eingerichtet "
                "werden – Anleitung siehe PRINTER_SETUP.md.",
                self._printer_name, list(printers.keys()) or ["(keine)"]
            )
        elif resolved != self._printer_name:
            logger.info(
                "Drucker '%s' nicht exakt gefunden – verwende stattdessen die "
                "CUPS-Warteschlange '%s'.",
                self._printer_name, resolved
            )
        self._target = resolved
        return resolved

    def _resolve_name(self, printers: dict) -> str | None:
        if not printers:
            return None
        if self._printer_name in printers:
            return self._printer_name
        wanted = self._printer_name.lower()
        for name in printers:
            if name.lower() == wanted:
                return name
        for name in printers:
            if wanted in name.lower() or name.lower() in wanted:
                return name
        if len(printers) == 1:
            return next(iter(printers))
        return None

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
        # Warteschlange jedes Mal neu auflösen – sie kann seit dem Start
        # eingerichtet oder umbenannt worden sein.
        target = self._refresh_target()

        if not self._conn:
            logger.error(
                "Drucker '%s' nicht erreichbar: CUPS-Verbindung nicht verfügbar. "
                "CUPS-Dienst prüfen: `sudo systemctl restart cups`",
                self._printer_name
            )
            return False

        if target is None:
            logger.error(
                "Druck abgebrochen: Keine CUPS-Warteschlange für '%s' eingerichtet. "
                "Einmalige Einrichtung nötig (siehe PRINTER_SETUP.md), z. B.: "
                "`sudo lpadmin -p %s -E -v <geraete-uri> -m <treiber>`",
                self._printer_name, self._printer_name
            )
            return False

        try:
            job_id = self._conn.printFile(
                target,
                str(path),
                "Fotobox",
                # SELPHY-Papier ist Postkarte 100×148 mm; "fit-to-page" für
                # klassische PPD-Queues, "print-scaling" für driverless/IPP.
                {"fit-to-page": "true", "print-scaling": "fill", "media": "Postcard"},
            )
            logger.info("Druckauftrag gesendet: Job-ID=%s, Datei=%s", job_id, path)
            return True
        except cups.IPPError as e:
            logger.error(
                "Druckfehler (CUPS IPP %s): %s. "
                "Bitte prüfen: Drucker eingeschaltet? Kabel/WLAN verbunden? "
                "Papier eingelegt? CUPS-Status: `lpstat -p %s`",
                e.args[0] if e.args else "?", e, target
            )
            return False
        except Exception as e:
            logger.error(
                "Druckfehler (unbekannt): %s. "
                "CUPS-Log prüfen: `journalctl -u cups --since '5 minutes ago'`",
                e
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
            self._connect()
        target = self._refresh_target()
        if not self._conn or target is None:
            return False
        try:
            printers = self._conn.getPrinters()
            info  = printers.get(target, {})
            state = info.get("printer-state", 0)
            return state in (3, 4)  # 3 = idle, 4 = processing
        except Exception:
            return False
