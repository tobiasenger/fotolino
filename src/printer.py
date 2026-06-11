from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

try:
    import cups
    _CUPS_AVAILABLE = True
except ImportError:
    _CUPS_AVAILABLE = False
    logger.info("pycups nicht verfügbar – Drucken nur als Demo-Ausgabe möglich. "
                "Auf dem Pi installieren mit: sudo apt install -y python3-cups")

_DEMO_MSG = (
    "\n"
    "╔══════════════════════════════════════════════════════════╗\n"
    "║  DEMO-MODUS: Hier würde normalerweise ein Foto gedruckt  ║\n"
    "║  werden. Drucker wird nicht angesteuert.                 ║\n"
    "╚══════════════════════════════════════════════════════════╝"
)

# Druckoptionen für den Canon SELPHY CP1500 mit Gutenprint-5.3-PPD
# (Treiber "gutenprint.5.3://canon-cp1500/expert", siehe PRINTER_SETUP.md).
# Die Werte stammen aus dem PPD bzw. `lpoptions -p SELPHY -l`:
#   PageSize ........... Postcard (100×148 mm, KP-108IN-Papier);
#                        weitere PPD-Werte: w253h337 (L), w155h244 (Karte)
#   StpBorderless ...... randloser Druck (zieht die Ränder auf 0)
#   StpiShrinkOutput ... Expand = Bild auf die volle Seite aufziehen
#   StpImageType ....... Farbabstimmung für Fotos
#   fit-to-page ........ CUPS-Filter skaliert das JPEG auf die Seitengröße
# Unbekannte Optionen werden von CUPS ignoriert (z. B. falls die Queue mit
# dem "simple"-PPD statt "expert" angelegt wurde) – sie schaden also nicht.
_PRINT_OPTIONS = {
    "PageSize": "Postcard",
    "StpBorderless": "True",
    "StpiShrinkOutput": "Expand",
    "StpImageType": "Photo",
    "fit-to-page": "true",
}

# IPP-Job-Status (RFC 8011, Abschnitt 5.3.7)
_JOB_STATES = {
    3: "pending", 4: "held", 5: "processing", 6: "stopped",
    7: "canceled", 8: "aborted", 9: "completed",
}

# Nicht abgeschlossene Aufträge, die älter sind, gelten als hängen geblieben
# (ein SELPHY-Druck dauert ~45–60 s) und werden vor dem nächsten Druck
# verworfen, damit der neue Auftrag nicht dahinter feststeckt.
_STALE_JOB_SECONDS = 180


class Printer:
    def __init__(self, config_manager):
        self._cfg          = config_manager
        self._printer_name = config_manager.settings.get("printer_name", "SELPHY")
        self._conn         = None
        self._target       = None  # tatsächlicher CUPS-Warteschlangenname
        self._target_info  = {}    # CUPS-Attribute der Warteschlange (z. B. device-uri)
        self._usb_uri_warned = False
        self._uri_misconfigured = False  # SELPHY hängt am Standard-USB-Backend
        self._repair_attempted = False   # automatische Reparatur nur 1× je Lauf
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
            self._target_info = {}
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
        self._target_info = printers.get(resolved, {}) if resolved else {}

        # Fehlkonfiguration erkennen: Ein SELPHY am Standard-USB-Backend
        # bleibt bei 'Waiting for printer to become available' bzw. 'Daten
        # werden empfangen' hängen. Vor dem nächsten Druck versucht die App
        # einmalig, die Queue selbst umzustellen (_try_fix_device_uri).
        uri = self._target_info.get("device-uri", "")
        self._uri_misconfigured = bool(
            resolved and uri.startswith("usb://") and "selphy" in uri.lower())
        if self._uri_misconfigured and not self._usb_uri_warned:
            self._usb_uri_warned = True
            logger.warning(
                "Warteschlange '%s' nutzt das Standard-USB-Backend (%s). "
                "Der SELPHY braucht das Gutenprint-Backend "
                "'gutenprint53+usb://…', sonst hängen Druckaufträge. "
                "Reparatur: siehe PRINTER_FIX.md.",
                resolved, uri,
            )
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

        # Selbstheilung – läuft im Druck-Thread, darf also kurz blocken.
        if self._uri_misconfigured and not self._repair_attempted:
            self._repair_attempted = True
            if self._try_fix_device_uri(target):
                self._uri_misconfigured = False
        self._prepare_queue(target)

        logger.info(
            "Sende Druckauftrag: Warteschlange='%s', Geräte-URI='%s', "
            "Drucker-Status=%s, Datei='%s', Optionen=%s",
            target,
            self._target_info.get("device-uri", "?"),
            self._target_info.get("printer-state", "?"),
            path, _PRINT_OPTIONS,
        )
        try:
            job_id = self._conn.printFile(target, str(path), "Fotobox",
                                          dict(_PRINT_OPTIONS))
        except cups.IPPError as e:
            logger.error(
                "Druckfehler (CUPS IPP %s): %s. "
                "Bitte prüfen: Drucker eingeschaltet? USB-Kabel verbunden? "
                "Papier eingelegt? CUPS-Status: `lpstat -p %s`",
                e.args[0] if e.args else "?", e, target
            )
            return False
        except Exception as e:
            logger.error(
                "Druckfehler (unbekannt): %s. "
                "CUPS-Log prüfen: `journalctl -u cups --since '5 minutes ago'`",
                e, exc_info=True
            )
            return False

        if not job_id:
            logger.error(
                "CUPS hat den Druckauftrag für '%s' ohne Job-ID abgelehnt "
                "(Datei: %s).", target, path
            )
            return False
        logger.info("Druckauftrag angenommen: Job-ID=%s, Warteschlange='%s', "
                    "Datei='%s'", job_id, target, path)
        return self._verify_job(job_id)

    def _verify_job(self, job_id: int) -> bool:
        """Kurz nachprüfen, ob CUPS den angenommenen Auftrag auch verarbeitet.

        Läuft im Druck-Thread (nicht im GUI-Thread), darf also kurz blocken.
        Verworfene Aufträge (aborted/canceled/stopped) werden als Fehler
        gemeldet statt stillschweigend als Erfolg. Ein Auftrag, der nach der
        Wartezeit noch 'pending' ist, gilt weiter als angenommen (z. B. weil
        der vorige Druck noch läuft), wird aber mit der CUPS-Druckermeldung
        protokolliert – dort steht z. B. 'Waiting for printer to become
        available', wenn das USB-Backend den Drucker nicht öffnen kann.
        """
        attrs = {}
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                attrs = self._conn.getJobAttributes(job_id)
            except Exception as e:
                logger.warning(
                    "Job-Status von Auftrag %s nicht abfragbar (%s) – "
                    "Auftrag wurde aber von CUPS angenommen.", job_id, e
                )
                return True
            state = attrs.get("job-state", 0)
            if state in (5, 9):     # processing / completed
                logger.info("Druckauftrag %s wird verarbeitet (Status=%s).",
                            job_id, _JOB_STATES.get(state, state))
                return True
            if state in (6, 7, 8):  # stopped / canceled / aborted
                logger.error(
                    "Druckauftrag %s von CUPS verworfen: Status=%s, "
                    "Gründe=%s, Druckermeldung='%s'. Siehe PRINTER_SETUP.md "
                    "(Fehlersuche).",
                    job_id, _JOB_STATES.get(state, state),
                    attrs.get("job-state-reasons", "?"),
                    attrs.get("job-printer-state-message", ""),
                )
                return False
            time.sleep(0.5)

        state = attrs.get("job-state", 0)
        logger.warning(
            "Druckauftrag %s nach 5 s noch nicht gestartet (Status=%s, "
            "Druckermeldung='%s'). Falls die Meldung 'Waiting for printer to "
            "become available' lautet: USB-Kabel ab- und wieder anstecken "
            "bzw. Drucker aus- und einschalten (siehe PRINTER_FIX.md).",
            job_id, _JOB_STATES.get(state, state),
            attrs.get("job-printer-state-message", ""),
        )
        return True

    # ------------------------------------------------------------------
    # Queue-Selbstheilung
    # ------------------------------------------------------------------

    def _try_fix_device_uri(self, target: str) -> bool:
        """Queue einmalig vom Standard-USB-Backend auf das Gutenprint-
        SELPHY-Backend umstellen (wie `sudo lpadmin -p … -v gutenprint53+usb://…`).

        Klappt nur, wenn der App-Benutzer CUPS-Verwaltungsrechte hat
        (Gruppe `lpadmin`); andernfalls bleibt es bei der Warnung und der
        manuellen Reparatur nach PRINTER_FIX.md.
        """
        bad_uri = self._target_info.get("device-uri", "")
        try:
            # Nur das eine Backend abfragen – ein voller Geräte-Scan
            # (alle Backends) würde deutlich länger blockieren.
            devices = self._conn.getDevices(
                include_schemes=["gutenprint53+usb"], timeout=8)
        except Exception as e:
            logger.warning(
                "Gerätesuche für die automatische Queue-Reparatur "
                "fehlgeschlagen (%s) – manuelle Reparatur siehe "
                "PRINTER_FIX.md.", e)
            return False

        candidates = [u for u in devices if u.startswith("gutenprint53+usb://")]
        serial = bad_uri.rsplit("serial=", 1)[-1] if "serial=" in bad_uri else ""
        good_uri = next((u for u in candidates if serial and serial in u), None)
        if good_uri is None and len(candidates) == 1:
            good_uri = candidates[0]
        if good_uri is None:
            logger.warning(
                "Kein gutenprint53+usb-Gerät für die automatische Reparatur "
                "gefunden (Kandidaten: %s). Drucker einschalten/anstecken, "
                "sonst PRINTER_FIX.md beachten.", candidates or "(keine)")
            return False

        try:
            self._conn.setPrinterDevice(target, good_uri)
        except Exception as e:
            logger.warning(
                "Queue '%s' konnte nicht automatisch umgestellt werden (%s). "
                "Manuell ausführen: `sudo lpadmin -p %s -v \"%s\"` "
                "(siehe PRINTER_FIX.md).", target, e, target, good_uri)
            return False
        self._target_info["device-uri"] = good_uri
        logger.warning(
            "Warteschlange '%s' automatisch repariert: Geräte-URI von '%s' "
            "auf '%s' umgestellt.", target, bad_uri, good_uri)
        return True

    def _prepare_queue(self, target: str):
        """Warteschlange vor dem Druck in einen druckfähigen Zustand bringen.

        Räumt bekannte Folgen einer zuvor hängenden Queue auf. Jeder Schritt
        ist optional und scheitert nur mit Log-Eintrag, nie mit Exception:
          * Von CUPS gestoppte Queue (printer-state 5) wieder aktivieren.
          * Angehaltene/gestoppte sowie veraltete Aufträge verwerfen, damit
            der neue Druck nicht dahinter feststeckt.
        Frische 'pending'-Aufträge bleiben unangetastet: Bei Sitzungen kurz
        hintereinander druckt der SELPHY u. U. noch den vorigen Auftrag –
        ein pauschales cancel-all würde gültige Drucke vernichten.
        """
        if self._target_info.get("printer-state") == 5:    # 5 = stopped
            try:
                self._conn.enablePrinter(target)
                self._conn.acceptJobs(target)
                logger.warning(
                    "Gestoppte Warteschlange '%s' wieder aktiviert.", target)
            except Exception as e:
                logger.warning(
                    "Gestoppte Warteschlange '%s' konnte nicht reaktiviert "
                    "werden (%s). Manuell: `sudo cupsenable %s && "
                    "sudo cupsaccept %s`", target, e, target, target)

        try:
            jobs = self._conn.getJobs(which_jobs="not-completed")
        except Exception as e:
            logger.warning("CUPS-Jobliste nicht abfragbar: %s", e)
            return
        now = time.time()
        for job_id, attrs in jobs.items():
            if not str(attrs.get("job-printer-uri", "")).endswith("/" + target):
                continue
            state = attrs.get("job-state", 0)
            age = now - attrs.get("time-at-creation", now)
            if state in (4, 6) or age > _STALE_JOB_SECONDS:  # held/stopped/uralt
                try:
                    self._conn.cancelJob(job_id)
                    logger.warning(
                        "Hängenden Druckauftrag %s verworfen "
                        "(Status=%s, Alter=%.0f s).",
                        job_id, _JOB_STATES.get(state, state), age)
                except Exception as e:
                    logger.warning(
                        "Auftrag %s konnte nicht verworfen werden: %s",
                        job_id, e)

    def print_image(self, img: Image.Image) -> bool:
        """Save PIL image to a temp file and print it (CUPS copies it to its spool)."""
        if self.is_demo():
            print(_DEMO_MSG)
            logger.info("Demo-Modus aktiv: Druckvorgang übersprungen (Bild aus Speicher)")
            return True
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                img.save(tmp, "JPEG", quality=95)
            return self.print_collage(tmp_path)
        except Exception as e:
            logger.error("Druck aus Speicherbild fehlgeschlagen: %s", e, exc_info=True)
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
