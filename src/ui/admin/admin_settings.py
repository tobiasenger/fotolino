"""
Admin Settings tab (PyQt6).

Left sidebar: 6 tabs (Startscreen / Overlays / Aufnahme / Darstellung /
Gerät / Sicherung). Right: QStackedWidget with a QScrollArea per tab.

The tabs are rebuilt from the saved configuration every time the view is
shown (refresh()), so an imported configuration is reflected immediately.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)
from PIL import Image

from ...constants import COLLAGE_H, COLLAGE_W
from .. import theme
from ..widgets import FileSelectRow

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov"}
_BG_EXTS = _IMAGE_EXTS | _VIDEO_EXTS
_PNG_EXTS = {".png"}
_WAV_EXTS = {".wav"}

_TABS = ["Startscreen", "Overlays", "Aufnahme", "Darstellung", "Gerät", "Sicherung"]


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
            b.setStyleSheet(theme.TAB_BTN_STYLE)
            b.clicked.connect(lambda _, idx=i: self._show_tab(idx))
            side.addWidget(b)
            self._tab_btns[i] = b
        side.addStretch()
        save = QPushButton("Speichern")
        save.setStyleSheet(theme.BTN_STYLE)
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
        cfg = self.app.config.settings

        # --- Startscreen ---
        f = self._scroll_form()
        bg = cfg.get("idle_background", {})
        self._combo("bg_type", [("Bild", "image"), ("Video", "video")],
                    bg.get("type", "image"), f, "Hintergrundtyp:")
        self._file_row("bg_file", bg.get("file", ""), f,
                       "Hintergrunddatei:", _BG_EXTS, "Hintergrund")

        # --- Overlays (collage covers) ---
        f = self._scroll_form()
        f.addRow(QLabel(f"Collage-Overlays (PNG, {COLLAGE_W}×{COLLAGE_H} px):"))
        covers = cfg.get("collage_covers", {})
        for n in range(1, 5):
            self._file_row(f"cover_{n}", covers.get(str(n), ""), f,
                           f"{n} Foto(s):", _PNG_EXTS, "Overlay")

        # --- Aufnahme ---
        f = self._scroll_form()
        sounds = cfg.get("system_sounds", {})
        self._file_row("shutter_click", sounds.get("shutter_click", ""), f,
                       "Auslöser-Ton (WAV empfohlen):", _WAV_EXTS, "Auslöser-Ton")
        self._file_row("countdown_beep", sounds.get("countdown_beep", ""), f,
                       "Countdown-Ton (WAV empfohlen):", _WAV_EXTS, "Countdown-Ton")
        timing = cfg.get("capture_timing", {})
        self._entry("t_preview", timing.get("initial_preview_seconds", 2.0), f,
                    "Vorschau-Dauer (s):")
        self._entry("t_countdown", timing.get("countdown_from", 3), f, "Countdown ab:")
        self._combo("smile_enabled", [("Ja", True), ("Nein", False)],
                    timing.get("smile_enabled", True), f, "Lächeln-Hinweis aktiv:")
        self._entry("smile_text", timing.get("smile_text", "Lächeln!"), f,
                    "Lächeln-Text:")
        self._entry("t_smile", timing.get("smile_duration", 0.8), f, "Lächeln-Dauer (s):")
        self._entry("t_post", timing.get("post_photo_pause", 2.0), f, "Pause nach Foto (s):")
        self._entry("t_flash", timing.get("flash_duration", 0.15), f, "Blitz-Dauer (s):")
        self._combo("flash_enabled", [("Ja", True), ("Nein", False)],
                    cfg.get("flash_enabled", True), f, "Blitz-LED aktiv:")

        # --- Darstellung ---
        f = self._scroll_form()
        self._entry("loading_bar_color", cfg.get("loading_bar_color", "#FF6600"), f,
                    "Ladebalken-Farbe (#RRGGBB):")
        self._combo("progress_bar_enabled", [("Ja", True), ("Nein", False)],
                    cfg.get("progress_bar_enabled", True), f, "Ladebalken anzeigen:")
        self._entry("screen_width", cfg.get("screen_width", 1920), f, "Bildschirmbreite:")
        self._entry("screen_height", cfg.get("screen_height", 1080), f, "Bildschirmhöhe:")

        # --- Gerät ---
        f = self._scroll_form()
        pins = cfg.get("gpio", {})
        self._entry("gpio_pin_start_button", pins.get("pin_start_button", 17), f, "GPIO Start-Button:")
        self._entry("gpio_pin_admin_button", pins.get("pin_admin_button", 27), f, "GPIO Admin-Button:")
        self._entry("gpio_pin_led_flash", pins.get("pin_led_flash", 22), f, "GPIO Flash-LED:")
        self._entry("gpio_pin_led_ready", pins.get("pin_led_ready", 23), f, "GPIO Ready-LED:")
        self._entry("printer_name", cfg.get("printer_name", "SELPHY"), f, "CUPS-Druckername:")
        self._entry("usb_mount", cfg.get("usb_mount", "/media/usb"), f, "USB-Mount-Pfad:")
        self._combo("force_headphone_audio", [("Ja", True), ("Nein", False)],
                    cfg.get("force_headphone_audio", True), f,
                    "Audio auf Klinke zwingen:")
        self._combo("demo_mode", [("Aus", False), ("Ein", True)],
                    cfg.get("demo_mode", False), f, "Demo-Modus (kein Drucker):")

        cam_btn = QPushButton("Kamera testen")
        cam_btn.setStyleSheet(theme.BTN_STYLE)
        cam_btn.clicked.connect(lambda: self.app.switch_screen("camera_test"))
        f.addRow("", cam_btn)

        usb_btn = QPushButton("USB-Stick vorbereiten")
        usb_btn.setStyleSheet(theme.BTN_STYLE)
        usb_btn.setToolTip("Erstellt die Ordner 'Fotos' und 'Collagen' auf dem USB-Stick.")
        usb_btn.clicked.connect(self._prepare_usb)
        f.addRow("", usb_btn)

        # --- Sicherung ---
        f = self._scroll_form()
        f.addRow(QLabel("Konfiguration exportieren/importieren:"))
        exp = QPushButton("Konfiguration exportieren")
        exp.setStyleSheet(theme.BTN_STYLE)
        exp.clicked.connect(self._export_config)
        imp = QPushButton("Konfiguration importieren")
        imp.setStyleSheet(theme.BTN_STYLE)
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
            self.refresh()
            self.app.show_notification(
                "Konfiguration importiert. Bitte App neu starten.",
                duration=8.0, level="info")
        except (OSError, json.JSONDecodeError) as e:
            self.app.show_notification(f"Import fehlgeschlagen: {e}", duration=6.0, level="error")
