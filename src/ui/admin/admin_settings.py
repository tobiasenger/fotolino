"""
Admin Settings tab (PyQt6).

Left sidebar: 6 logically grouped tabs (Darstellung / Aufnahme / Zeiten /
Collage / Gerät / Sicherung), each tab divided into titled blocks with
separators. Right: QStackedWidget with a QScrollArea per tab.

The tabs are rebuilt from the saved configuration every time the view is
shown (refresh()), so an imported configuration is reflected immediately.
Saving reads fields by key, so moving a field to another tab never affects
the stored configuration.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)
from PIL import Image

from ...constants import COLLAGE_H, COLLAGE_W, SCENE_DURATION_RANGES
from ..widgets import FileSelectRow, add_form_section, make_hint, set_kind

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov"}
_BG_EXTS = _IMAGE_EXTS | _VIDEO_EXTS
_PNG_EXTS = {".png"}
_WAV_EXTS = {".wav"}

_TABS = ["Darstellung", "Aufnahme", "Zeiten", "Collage", "Gerät", "Sicherung"]

_DURATION_FIELDS = [
    ("greeting_min", "Begrüßung minimal"),
    ("greeting_max", "Begrüßung maximal"),
    ("collage", "Collage-Dauer"),
    ("print", "Druck-Dauer"),
]


class AdminSettings(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._fields: dict = {}
        self._active_idx = 0

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
            set_kind(b, "tab")
            b.clicked.connect(lambda _, idx=i: self._show_tab(idx))
            side.addWidget(b)
            self._tab_btns[i] = b
        side.addStretch()
        save = QPushButton("Speichern")
        set_kind(save, "primary")
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
    # Form builders
    # ------------------------------------------------------------------

    def _scroll_form(self) -> QFormLayout:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(inner)
        self._stack.addWidget(scroll)
        return form

    def _entry(self, key: str, value, form: QFormLayout, label: str):
        line = QLineEdit(str(value))
        self._fields[key] = line
        form.addRow(label, line)

    def _file_row(self, key: str, value, form: QFormLayout, label: str,
                  exts: set, kind: str):
        row = FileSelectRow(self.app.config, exts, kind, value=value)
        self._fields[key] = row
        form.addRow(label, row)

    def _combo(self, key: str, options: list[tuple], current, form, label: str):
        combo = QComboBox()
        for text, data in options:
            combo.addItem(text, data)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._fields[key] = combo
        form.addRow(label, combo)

    def _build_tabs(self):
        """One block per _TABS entry, in the same order. Blocks within a tab
        are separated via add_form_section()."""
        cfg = self.app.config.settings

        # --- Darstellung (Startbildschirm, Ladebalken, Bildschirm) ---
        f = self._scroll_form()
        add_form_section(f, "Startbildschirm", first=True)
        bg = cfg.get("idle_background", {})
        self._combo("bg_type", [("Bild", "image"), ("Video", "video")],
                    bg.get("type", "image"), f, "Hintergrundtyp:")
        self._file_row("bg_file", bg.get("file", ""), f,
                       "Hintergrunddatei:", _BG_EXTS, "Hintergrund")

        add_form_section(f, "Ladebalken")
        self._entry("loading_bar_color", cfg.get("loading_bar_color", "#FF6600"), f,
                    "Farbe (#RRGGBB):")
        self._combo("progress_bar_enabled", [("Ja", True), ("Nein", False)],
                    cfg.get("progress_bar_enabled", True), f, "Anzeigen:")

        add_form_section(f, "Bildschirm")
        self._entry("screen_width", cfg.get("screen_width", 1920), f, "Breite (px):")
        self._entry("screen_height", cfg.get("screen_height", 1080), f, "Höhe (px):")

        # --- Aufnahme (Ablauf, Lächeln, Töne, Blitz) ---
        f = self._scroll_form()
        timing = cfg.get("capture_timing", {})
        add_form_section(f, "Ablauf", first=True)
        self._entry("t_preview", timing.get("initial_preview_seconds", 2.0), f,
                    "Vorschau-Dauer (s):")
        self._entry("t_countdown", timing.get("countdown_from", 3), f, "Countdown ab:")
        self._entry("t_post", timing.get("post_photo_pause", 2.0), f,
                    "Pause nach Foto (s):")

        add_form_section(f, "Lächeln-Hinweis")
        self._combo("smile_enabled", [("Ja", True), ("Nein", False)],
                    timing.get("smile_enabled", True), f, "Aktiv:")
        self._entry("smile_text", timing.get("smile_text", "Lächeln!"), f, "Text:")
        self._entry("t_smile", timing.get("smile_duration", 0.8), f, "Dauer (s):")

        add_form_section(f, "Töne")
        sounds = cfg.get("system_sounds", {})
        self._file_row("shutter_click", sounds.get("shutter_click", ""), f,
                       "Auslöser-Ton (WAV empfohlen):", _WAV_EXTS, "Auslöser-Ton")
        self._file_row("countdown_beep", sounds.get("countdown_beep", ""), f,
                       "Countdown-Ton (WAV empfohlen):", _WAV_EXTS, "Countdown-Ton")

        add_form_section(f, "Blitz-LED")
        self._combo("flash_enabled", [("Ja", True), ("Nein", False)],
                    cfg.get("flash_enabled", True), f, "Aktiv:")
        self._entry("t_flash", timing.get("flash_duration", 0.15), f, "Dauer (s):")

        # --- Zeiten (scene durations) ---
        f = self._scroll_form()
        durations = self.app.config.scene_durations()

        def _dur_row(section: str, keys: list[str], first: bool = False):
            add_form_section(f, section, first=first)
            for key, label in _DURATION_FIELDS:
                if key in keys:
                    lo, hi = SCENE_DURATION_RANGES[key]
                    self._entry(f"dur_{key}", f"{durations[key]:g}", f,
                                f"{label} ({lo}–{hi} s):")

        _dur_row("Begrüßung", ["greeting_min", "greeting_max"], first=True)
        f.addRow(make_hint(
            "Die Mediendauer (Audio/Video) der Begrüßungsszene muss zwischen "
            "Minimal- und Maximalwert liegen."))
        _dur_row("Collage & Druck", ["collage", "print"])
        f.addRow(make_hint(
            "Collage/Druck: Die Szene dauert exakt die eingestellte Zeit; das "
            "Audio spielt einmal bis zum Ende und darf höchstens so lang sein.\n"
            "Änderungen werden nur übernommen, wenn alle vorhandenen Szenen in "
            "die neuen Grenzen passen."))

        # --- Collage (overlays) ---
        f = self._scroll_form()
        add_form_section(f, "Collage-Overlays", first=True)
        f.addRow(make_hint(
            f"PNG mit Transparenz, exakt {COLLAGE_W}×{COLLAGE_H} px – wird je "
            "nach Fotoanzahl über die Collage gelegt."))
        covers = cfg.get("collage_covers", {})
        for n in range(1, 5):
            self._file_row(f"cover_{n}", covers.get(str(n), ""), f,
                           f"{n} Foto(s):", _PNG_EXTS, "Overlay")

        # --- Gerät (Drucker, Speicher, Audio, GPIO, Wartung) ---
        f = self._scroll_form()
        add_form_section(f, "Drucker", first=True)
        self._entry("printer_name", cfg.get("printer_name", "SELPHY"), f,
                    "CUPS-Druckername:")
        self._combo("demo_mode", [("Aus", False), ("Ein", True)],
                    cfg.get("demo_mode", False), f, "Demo-Modus (kein Drucker):")

        add_form_section(f, "Speicher")
        self._entry("usb_mount", cfg.get("usb_mount", "/media/usb"), f,
                    "USB-Mount-Pfad:")
        usb_btn = QPushButton("USB-Stick vorbereiten")
        usb_btn.setToolTip("Erstellt die Ordner 'Fotos' und 'Collagen' auf dem USB-Stick.")
        usb_btn.clicked.connect(self._prepare_usb)
        f.addRow("", usb_btn)

        add_form_section(f, "Audio")
        self._combo("force_headphone_audio", [("Ja", True), ("Nein", False)],
                    cfg.get("force_headphone_audio", True), f,
                    "Audio auf Klinke zwingen:")

        add_form_section(f, "GPIO-Pins")
        pins = cfg.get("gpio", {})
        self._entry("gpio_pin_start_button", pins.get("pin_start_button", 17), f,
                    "Start-Button:")
        self._entry("gpio_pin_admin_button", pins.get("pin_admin_button", 27), f,
                    "Admin-Button:")
        self._entry("gpio_pin_led_flash", pins.get("pin_led_flash", 22), f,
                    "Flash-LED:")
        self._entry("gpio_pin_led_ready", pins.get("pin_led_ready", 23), f,
                    "Ready-LED:")
        f.addRow(make_hint("Pin-Änderungen werden beim nächsten Start übernommen."))

        add_form_section(f, "Wartung")
        cam_btn = QPushButton("Kamera testen")
        cam_btn.clicked.connect(lambda: self.app.switch_screen("camera_test"))
        f.addRow("", cam_btn)

        # --- Sicherung ---
        f = self._scroll_form()
        add_form_section(f, "Konfiguration", first=True)
        f.addRow(make_hint(
            "Sichert alle Einstellungen, Szenen und Pfade in eine JSON-Datei "
            "bzw. stellt sie daraus wieder her. Nach einem Import die App neu "
            "starten."))
        exp = QPushButton("Konfiguration exportieren")
        exp.clicked.connect(self._export_config)
        imp = QPushButton("Konfiguration importieren")
        imp.clicked.connect(self._import_config)
        f.addRow("", exp)
        f.addRow("", imp)

    def _show_tab(self, idx: int):
        self._active_idx = idx
        for i, b in self._tab_btns.items():
            b.setChecked(i == idx)
        self._stack.setCurrentIndex(idx)

    def refresh(self):
        """Rebuild all fields from the saved configuration."""
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._fields.clear()
        self._build_tabs()
        self._show_tab(self._active_idx)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _get(self, key: str, cast=str):
        w = self._fields.get(key)
        if isinstance(w, (QLineEdit, FileSelectRow)):
            try:
                return cast(w.text().strip())
            except (ValueError, AttributeError):
                return None
        if isinstance(w, QComboBox):
            return w.currentData()
        return None

    def _save(self):
        cfg = self.app.config.settings

        bg = cfg.setdefault("idle_background", {})
        bg["type"] = self._get("bg_type") or "image"
        bg["file"] = self._get("bg_file") or ""

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
        timing["smile_enabled"] = bool(self._get("smile_enabled"))
        timing["smile_text"] = self._get("smile_text") or "Lächeln!"
        timing["smile_duration"] = self._get("t_smile", float) or 0.8
        timing["post_photo_pause"] = self._get("t_post", float) or 2.0
        timing["flash_duration"] = self._get("t_flash", float) or 0.15
        cfg["flash_enabled"] = bool(self._get("flash_enabled"))

        duration_error = self._apply_scene_durations(cfg)

        cfg["loading_bar_color"] = self._get("loading_bar_color") or "#FF6600"
        cfg["progress_bar_enabled"] = bool(self._get("progress_bar_enabled"))
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
        cfg["force_headphone_audio"] = bool(self._get("force_headphone_audio"))
        cfg["demo_mode"] = bool(self._get("demo_mode"))

        self.app.config.save_settings()
        if duration_error:
            self.app.show_notification(
                f"Einstellungen gespeichert, aber: {duration_error}",
                duration=12.0, level="warning")
        else:
            self.app.show_notification("Einstellungen gespeichert.", duration=3.0, level="info")

    def _apply_scene_durations(self, cfg: dict) -> str | None:
        """Validate and apply the "Zeiten" tab. Returns an error text (and
        leaves the stored durations untouched) if the input is out of range
        or existing scenes would no longer fit the new limits."""
        old = self.app.config.scene_durations()
        new = {}
        for key, label in _DURATION_FIELDS:
            lo, hi = SCENE_DURATION_RANGES[key]
            value = self._get(f"dur_{key}", float)
            if value is None or not lo <= value <= hi:
                return f"{label}: Wert muss zwischen {lo} und {hi} Sekunden liegen."
            new[key] = value
        if new == old:
            return None
        bad = self.app.config.scenes_violating_durations(new)
        if bad:
            return ("Zeit-Änderung nicht übernommen. Folgende Szenen passen "
                    "nicht in die neuen Grenzen und müssen zuerst gelöscht "
                    "werden: " + ", ".join(bad))
        cfg["scene_durations"] = new
        return None

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
    # Backup / restore
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
            self.app.config.reload()   # fill in missing defaults (older exports)
            self.refresh()
            bad = self.app.config.scenes_violating_durations(
                self.app.config.scene_durations())
            if bad:
                self.app.show_notification(
                    "Konfiguration importiert. Achtung: Folgende Szenen passen "
                    "nicht in die konfigurierten Zeiten und müssen gelöscht oder "
                    "angepasst werden: " + ", ".join(bad)
                    + ". Bitte App neu starten.",
                    duration=15.0, level="warning")
            else:
                self.app.show_notification(
                    "Konfiguration importiert. Bitte App neu starten.",
                    duration=8.0, level="info")
        except (OSError, json.JSONDecodeError) as e:
            self.app.show_notification(f"Import fehlgeschlagen: {e}", duration=6.0, level="error")
