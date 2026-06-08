"""
Admin Settings tab (PyQt6).

Left sidebar: 6 tabs (Startscreen / Overlays / Aufnahme / Darstellung / Gerät / Sicherung).
Right: QStackedWidget with a QScrollArea per tab; each tab uses a QFormLayout.

File-format validation:
  * Shutter click: WAV only (QSoundEffect) – red warning if MP3/OGG selected.
  * Background image/video: .jpg/.jpeg/.png or .mp4/.avi/.mov.
  * Collage overlays: .png (1800×1200 validated on save).
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QStackedWidget, QScrollArea, QFileDialog,
)
from PyQt6.QtCore import Qt
from PIL import Image

from ...constants import COLLAGE_W, COLLAGE_H
from .file_dialog import open_file_dialog

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov"}
_BG_EXTS = _IMAGE_EXTS | _VIDEO_EXTS
_PNG_EXTS = {".png"}
_WAV_EXTS = {".wav"}

_TABS = ["Startscreen", "Overlays", "Aufnahme", "Darstellung", "Gerät", "Sicherung"]

_BTN = (
    "QPushButton { background: #2a2a50; color: white; border: 1px solid #444488; "
    "border-radius: 5px; padding: 8px 14px; } QPushButton:hover { border-color: #ff6600; }"
)
_TAB_BTN = (
    "QPushButton { background: #2a2a50; color: white; border: none; border-radius: 5px; "
    "padding: 10px; text-align: left; } QPushButton:checked { background: #ff6600; }")


class AdminSettings(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._fields: dict = {}
        self._warns: dict = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Sidebar
        side = QVBoxLayout()
        side.setSpacing(6)
        self._tab_btns = {}
        for i, name in enumerate(_TABS):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setStyleSheet(_TAB_BTN)
            b.clicked.connect(lambda _, idx=i: self._show_tab(idx))
            side.addWidget(b)
            self._tab_btns[i] = b
        side.addStretch()
        save = QPushButton("Speichern")
        save.setStyleSheet(_BTN)
        save.clicked.connect(self._save)
        side.addWidget(save)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(200)
        root.addWidget(side_w)

        # Content
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        self._build_tabs()
        self._show_tab(0)

    # ------------------------------------------------------------------

    def _scroll_form(self) -> tuple[QScrollArea, QFormLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(inner)
        self._stack.addWidget(scroll)
        return scroll, form

    def _entry(self, key: str, value, form: QFormLayout, label: str):
        line = QLineEdit(str(value))
        self._fields[key] = line
        form.addRow(label, line)
        return line

    def _file_row(self, key: str, value, form: QFormLayout, label: str,
                  exts: set, kind: str):
        line = QLineEdit(str(value))
        browse = QPushButton("…")
        browse.setStyleSheet(_BTN)
        warn = QLabel("")
        warn.setStyleSheet("color: #ff6060;")
        warn.setWordWrap(True)

        def do_browse():
            base = str(self.app.config.resolve_asset("assets"))
            sel = open_file_dialog(self, base, f"{kind} auswählen", exts)
            if not sel:
                return
            try:
                rel = Path(sel).resolve().relative_to(
                    self.app.config.resolve_asset("").resolve())
                line.setText(str(rel))
            except Exception:
                line.setText(sel)
            self._validate(line, exts, kind, warn)

        browse.clicked.connect(do_browse)
        line.textChanged.connect(lambda: self._validate(line, exts, kind, warn))

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(line, 1)
        lay.addWidget(browse)

        self._fields[key] = line
        self._warns[key] = warn
        form.addRow(label, row)
        form.addRow("", warn)
        self._validate(line, exts, kind, warn)
        return line

    @staticmethod
    def _validate(line: QLineEdit, exts: set, kind: str, warn: QLabel):
        path = line.text().strip()
        if path and Path(path).suffix.lower() not in exts:
            allowed = ", ".join(sorted(exts))
            warn.setText(f"Warnung: {kind} sollte eines dieser Formate sein: {allowed}")
        else:
            warn.setText("")

    def _combo(self, key: str, options: list[tuple[str, object]], current, form, label):
        combo = QComboBox()
        for text, data in options:
            combo.addItem(text, data)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._fields[key] = combo
        form.addRow(label, combo)
        return combo

    # ------------------------------------------------------------------

    def _build_tabs(self):
        cfg = self.app.config.settings

        # --- Startscreen ---
        _, f = self._scroll_form()
        bg = cfg.get("idle_background", {})
        self._combo("bg_type", [("Bild", "image"), ("Video", "video")],
                    bg.get("type", "image"), f, "Hintergrundtyp:")
        self._file_row("bg_file", bg.get("file", ""), f,
                       "Hintergrunddatei:", _BG_EXTS, "Hintergrund")

        # --- Overlays (collage covers) ---
        _, f = self._scroll_form()
        f.addRow(QLabel("Collage-Overlays (PNG, 1800×1200 px):"))
        covers = cfg.get("collage_covers", {})
        for n in range(1, 5):
            self._file_row(f"cover_{n}", covers.get(str(n), ""), f,
                           f"{n} Foto(s):", _PNG_EXTS, "Overlay")

        # --- Aufnahme ---
        _, f = self._scroll_form()
        sounds = cfg.get("system_sounds", {})
        self._file_row("shutter_click", sounds.get("shutter_click", ""), f,
                       "Auslöser-Ton (NUR WAV):", _WAV_EXTS, "Auslöser-Ton")
        self._file_row("countdown_beep", sounds.get("countdown_beep", ""), f,
                       "Countdown-Ton (NUR WAV):", _WAV_EXTS, "Countdown-Ton")
        timing = cfg.get("capture_timing", {})
        self._entry("t_preview", timing.get("initial_preview_seconds", 2.0), f,
                    "Vorschau-Dauer (s):")
        self._entry("t_countdown", timing.get("countdown_from", 3), f, "Countdown ab:")
        self._entry("t_smile", timing.get("smile_duration", 0.8), f, "Lächeln-Dauer (s):")
        self._entry("t_post", timing.get("post_photo_pause", 2.0), f, "Pause nach Foto (s):")
        self._entry("t_flash", timing.get("flash_duration", 0.15), f, "Blitz-Dauer (s):")
        self._combo("flash_enabled", [("Ja", True), ("Nein", False)],
                    cfg.get("flash_enabled", True), f, "Blitz-LED aktiv:")

        # --- Darstellung ---
        _, f = self._scroll_form()
        self._entry("loading_bar_color", cfg.get("loading_bar_color", "#FF6600"), f,
                    "Ladebalken-Farbe (#RRGGBB):")
        self._entry("screen_width", cfg.get("screen_width", 1920), f, "Bildschirmbreite:")
        self._entry("screen_height", cfg.get("screen_height", 1080), f, "Bildschirmhöhe:")

        # --- Gerät ---
        _, f = self._scroll_form()
        pins = cfg.get("gpio", {})
        self._entry("gpio_pin_start_button", pins.get("pin_start_button", 17), f, "GPIO Start-Button:")
        self._entry("gpio_pin_admin_button", pins.get("pin_admin_button", 27), f, "GPIO Admin-Button:")
        self._entry("gpio_pin_led_flash", pins.get("pin_led_flash", 22), f, "GPIO Flash-LED:")
        self._entry("gpio_pin_led_ready", pins.get("pin_led_ready", 23), f, "GPIO Ready-LED:")
        self._entry("printer_name", cfg.get("printer_name", "SELPHY"), f, "CUPS-Druckername:")
        self._entry("usb_mount", cfg.get("usb_mount", "/media/usb"), f, "USB-Mount-Pfad:")
        self._combo("demo_mode", [("Aus", False), ("Ein", True)],
                    cfg.get("demo_mode", False), f, "Demo-Modus (kein Drucker):")
        cam_btn = QPushButton("Kamera testen")
        cam_btn.setStyleSheet(_BTN)
        cam_btn.clicked.connect(lambda: self.app.switch_screen("camera_test"))
        f.addRow("", cam_btn)

        usb_btn = QPushButton("USB-Stick vorbereiten")
        usb_btn.setStyleSheet(_BTN)
        usb_btn.setToolTip(
            "Erstellt die Ordner 'Fotos' und 'Collagen' auf dem USB-Stick."
        )
        usb_btn.clicked.connect(self._prepare_usb)
        f.addRow("", usb_btn)

        # --- Sicherung ---
        _, f = self._scroll_form()
        f.addRow(QLabel("Konfiguration exportieren/importieren:"))
        exp = QPushButton("Konfiguration exportieren")
        exp.setStyleSheet(_BTN)
        exp.clicked.connect(self._export_config)
        imp = QPushButton("Konfiguration importieren")
        imp.setStyleSheet(_BTN)
        imp.clicked.connect(self._import_config)
        f.addRow("", exp)
        f.addRow("", imp)

    def _show_tab(self, idx: int):
        for i, b in self._tab_btns.items():
            b.setChecked(i == idx)
        self._stack.setCurrentIndex(idx)

    def refresh(self):
        # Rebuild fields from current config (e.g. after import).
        pass

    # ------------------------------------------------------------------

    def _get(self, key: str, cast=str):
        w = self._fields.get(key)
        if isinstance(w, QLineEdit):
            try:
                return cast(w.text().strip())
            except (ValueError, AttributeError):
                return None
        if isinstance(w, QComboBox):
            return w.currentData()
        return None

    def _save(self):
        cfg = self.app.config.settings

        cfg.setdefault("idle_background", {})
        cfg["idle_background"]["type"] = self._get("bg_type") or "image"
        cfg["idle_background"]["file"] = self._get("bg_file") or ""

        covers = cfg.setdefault("collage_covers", {})
        for n in range(1, 5):
            covers[str(n)] = self._get(f"cover_{n}") or ""
            self._validate_cover_size(covers[str(n)], n)

        sounds = cfg.setdefault("system_sounds", {})
        sounds["shutter_click"] = self._get("shutter_click") or ""
        sounds["countdown_beep"] = self._get("countdown_beep") or ""

        timing = cfg.setdefault("capture_timing", {})
        timing["initial_preview_seconds"] = self._get("t_preview", float) or 2.0
        timing["countdown_from"] = self._get("t_countdown", int) or 3
        timing["smile_duration"] = self._get("t_smile", float) or 0.8
        timing["post_photo_pause"] = self._get("t_post", float) or 2.0
        timing["flash_duration"] = self._get("t_flash", float) or 0.15
        cfg["flash_enabled"] = bool(self._get("flash_enabled"))

        cfg["loading_bar_color"] = self._get("loading_bar_color") or "#FF6600"
        sw = self._get("screen_width", int)
        sh = self._get("screen_height", int)
        if sw:
            cfg["screen_width"] = sw
        if sh:
            cfg["screen_height"] = sh

        pins = cfg.setdefault("gpio", {})
        for key in ("pin_start_button", "pin_admin_button", "pin_led_flash", "pin_led_ready"):
            val = self._get(f"gpio_{key}", int)
            if val is not None:
                pins[key] = val
        cfg["printer_name"] = self._get("printer_name") or "SELPHY"
        cfg["usb_mount"] = self._get("usb_mount") or "/media/usb"
        cfg["demo_mode"] = bool(self._get("demo_mode"))

        self.app.config.save_settings()

        # Warn if a system sound is not WAV.
        for key, label in (("shutter_click", "Auslöser-Ton"), ("countdown_beep", "Countdown-Ton")):
            val = sounds.get(key, "")
            if val and Path(val).suffix.lower() != ".wav":
                self.app.show_notification(
                    f"{label}: '{val}' ist kein WAV – Systemtöne benötigen WAV-Format.",
                    duration=8.0, level="warning")

        self.app.show_notification("Einstellungen gespeichert.", duration=3.0, level="info")

    def _validate_cover_size(self, rel: str, count: int):
        if not rel:
            return
        p = self.app.config.resolve_asset(rel)
        if not p.exists():
            return
        try:
            img = Image.open(p)
            if img.size != (COLLAGE_W, COLLAGE_H):
                self.app.show_notification(
                    f"Overlay {count}: muss {COLLAGE_W}×{COLLAGE_H} px sein "
                    f"(ist {img.size[0]}×{img.size[1]}).",
                    duration=8.0, level="warning")
        except Exception:
            pass

    def _prepare_usb(self):
        try:
            msg = self.app.storage.prepare_usb()
            self.app.show_notification(msg, duration=6.0, level="info")
        except IOError as e:
            self.app.show_notification(str(e), duration=8.0, level="error")

    # ------------------------------------------------------------------

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Konfiguration exportieren", str(Path.home() / "fotobox_config.json"),
            "JSON (*.json)")
        if not path:
            return
        data = {
            "settings": self.app.config.settings,
            "scenes": self.app.config.scenes,
            "paths": self.app.config.paths,
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            self.app.show_notification("Konfiguration exportiert.", duration=4.0, level="info")
        except OSError as e:
            self.app.show_notification(f"Export fehlgeschlagen: {e}", duration=6.0, level="error")

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Konfiguration importieren", str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if "settings" in data:
                self.app.config.settings = data["settings"]
                self.app.config.save_settings()
            if "scenes" in data:
                self.app.config.scenes = data["scenes"]
                self.app.config.save_scenes()
            if "paths" in data:
                self.app.config.paths = data["paths"]
                self.app.config.save_paths()
            self.app.show_notification(
                "Konfiguration importiert. Bitte App neu starten.",
                duration=8.0, level="info")
        except (OSError, json.JSONDecodeError) as e:
            self.app.show_notification(f"Import fehlgeschlagen: {e}", duration=6.0, level="error")
