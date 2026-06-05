"""
Admin Settings tab – restructured into four clear groups:
  ▸ Startscreen        – background type (image / video loop) + file browser
  ▸ Collage-Overlays   – PNG upload per slot (1–4 photos) with file browser + size validation
  ▸ Darstellung        – loading bar visibility and colour
  ▸ Betrieb            – demo mode, flash LED, printer name, USB path
  ▸ GPIO-Pins          – four pin numbers in a compact inline grid

All file pickers use the shared open_file_dialog helper (pygame_gui version-safe).
"""
from __future__ import annotations
from pathlib import Path

import pygame
import pygame_gui
from PIL import Image

from ...constants import SCREEN_W, SCREEN_H, COLLAGE_W, COLLAGE_H
from ..base_screen import get_font
from .file_dialog import open_file_dialog

_PROJECT_ROOT = Path(__file__).parents[3]

_TOP    = 70
_MARGIN = 20
_W      = SCREEN_W - 2 * _MARGIN   # full panel width
_H      = SCREEN_H - _TOP - _MARGIN

# Two-column split
_L_X  = _MARGIN + 10          # left column x
_L_W  = 860                   # left column width
_R_X  = _L_X + _L_W + 30     # right column x
_R_W  = _W - _L_W - 60       # right column width

# File-entry widths (entry + browse button side by side)
_BROWSE_W = 110
_L_ENTRY  = _L_W - _BROWSE_W - 10  # entry width in left column
_R_ENTRY  = min(420, _R_W - 20)    # entry width in right column (no browse)
_PIN_W    = 80                       # GPIO pin entry width

# Allowed extensions per field type
_EXT = {
    "image":      {".jpg", ".jpeg", ".png"},
    "video":      {".mp4", ".avi", ".mov"},
    "cover_png":  {".png"},
}

# Asset subdirs for the file dialog start path
_ASSET_DIR = {
    "image":     "assets/backgrounds",
    "video":     "assets/backgrounds",
    "cover_png": "assets/CollageCovers",
}


def _section(text: str) -> str:
    return f"▸  {text}"


class AdminSettings:
    def __init__(self, app, manager: pygame_gui.UIManager):
        self.app     = app
        self._mgr    = manager
        self._active = False
        self._widgets: list = []
        self._fields:  dict = {}
        self._status_msg = ""
        self._status_ok  = True

        # File dialog state
        self._file_dialog             = None
        self._file_dialog_target: str | None = None

    # ------------------------------------------------------------------

    def show(self):
        self._active = True
        self._build()

    def hide(self):
        self._active = False
        self._kill_all()

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        if not self._active:
            return

        # File picked from dialog
        if event.type == pygame_gui.UI_FILE_DIALOG_PATH_PICKED:
            self._on_file_picked(event.text)
            self._file_dialog = None
            self._file_dialog_target = None
            return

        # Background type changed → update hint label text
        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if event.ui_element == self._fields.get("bg_type"):
                is_video = event.text == "Video-Loop"
                lbl = self._fields.get("bg_file_hint")
                if lbl:
                    lbl.set_text("Videodatei (.mp4):" if is_video else "Bilddatei (.jpg / .png):")
                return
            return

        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return
        el = event.ui_element

        if el == self._fields.get("save_btn"):
            self._save(); return

        if el == self._fields.get("export_btn"):
            self._export_config(); return

        if el == self._fields.get("import_btn"):
            dd = self._fields.get("import_dd")
            name = getattr(dd, "selected_option", None)
            if name:
                self._import_config(name)
            return

        # Browse buttons
        for key in ("bg_file", "cover_1", "cover_2", "cover_3", "cover_4"):
            if el == self._fields.get(f"browse_{key}"):
                self._open_dialog(key); return

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        if not self._active:
            return
        # Status bar at bottom
        if self._status_msg:
            color = (80, 210, 100) if self._status_ok else (220, 60, 60)
            font  = get_font(24)
            surf  = font.render(self._status_msg, True, color)
            surface.blit(surf, (_MARGIN + 20, SCREEN_H - 48))

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _kill_all(self):
        for w in self._widgets:
            try: w.kill()
            except Exception: pass
        self._widgets.clear()
        self._fields.clear()
        if self._file_dialog:
            try: self._file_dialog.kill()
            except Exception: pass
            self._file_dialog = None

    def _build(self):
        self._kill_all()
        cfg = self.app.config.settings

        # ── helpers ──────────────────────────────────────────────────────

        def reg(w):
            self._widgets.append(w)
            return w

        def lbl(text, x, y, width=380, height=28):
            return reg(pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(x, y, width, height),
                text=text, manager=self._mgr,
            ))

        def section_lbl(text, x, y, width=None):
            w = width or (_L_W if x < _R_X else _R_W)
            return reg(pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(x, y, w, 34),
                text=_section(text), manager=self._mgr,
            ))

        def entry(key, value, x, y, width=_R_ENTRY, height=40):
            e = reg(pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(x, y, width, height),
                manager=self._mgr,
            ))
            e.set_text(str(value))
            self._fields[key] = e
            return e

        def entry_with_browse(entry_key, browse_key, value, x, y):
            e = reg(pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(x, y, _L_ENTRY, 40),
                manager=self._mgr,
            ))
            e.set_text(str(value))
            self._fields[entry_key] = e
            btn = reg(pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(x + _L_ENTRY + 10, y, _BROWSE_W, 40),
                text="📂 Suchen", manager=self._mgr,
            ))
            self._fields[f"browse_{browse_key}"] = btn
            return e, btn

        def dropdown(key, options, selected, x, y, width=220, height=44):
            if selected not in options:
                selected = options[0]
            dd = reg(pygame_gui.elements.UIDropDownMenu(
                options_list=options, starting_option=selected,
                relative_rect=pygame.Rect(x, y, width, height),
                manager=self._mgr,
            ))
            self._fields[key] = dd
            return dd

        covers    = cfg.get("collage_covers", {})
        idle_bg   = cfg.get("idle_background", {})
        gpio_pins = cfg.get("gpio", {})

        # ══════════════════════════════════════════════════════════════════
        # LEFT COLUMN
        # ══════════════════════════════════════════════════════════════════
        x, y = _L_X, _TOP + 14

        # ── STARTSCREEN ──────────────────────────────────────────────────
        section_lbl("STARTSCREEN", x, y); y += 42
        lbl("Hintergrundtyp:", x, y, _L_W); y += 30
        bg_type_val = "Video-Loop" if idle_bg.get("type") == "video" else "Bild (statisch)"
        dropdown("bg_type", ["Bild (statisch)", "Video-Loop"], bg_type_val, x, y, 260); y += 52

        is_bg_video = idle_bg.get("type") == "video"
        bg_hint_text = "Videodatei (.mp4):" if is_bg_video else "Bilddatei (.jpg / .png):"
        bg_hint = reg(pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x, y, _L_W, 28),
            text=bg_hint_text, manager=self._mgr,
        ))
        self._fields["bg_file_hint"] = bg_hint; y += 30
        entry_with_browse("bg_file", "bg_file", idle_bg.get("file", ""), x, y); y += 52

        y += 16  # gap between groups

        # ── COLLAGE-OVERLAYS ─────────────────────────────────────────────
        section_lbl("COLLAGE-OVERLAYS  (PNG, 1800×1200 px)", x, y); y += 42
        for n in range(1, 5):
            plural = "Foto" if n == 1 else "Fotos"
            lbl(f"{n} {plural}:", x, y, _L_W); y += 28
            cur = covers.get(str(n), "")
            entry_with_browse(f"cover_{n}", f"cover_{n}", cur, x, y); y += 50

        # ══════════════════════════════════════════════════════════════════
        # RIGHT COLUMN
        # ══════════════════════════════════════════════════════════════════
        x, y = _R_X, _TOP + 14

        # ── DARSTELLUNG ──────────────────────────────────────────────────
        section_lbl("DARSTELLUNG", x, y, _R_W); y += 42
        lbl("Ladebalken anzeigen:", x, y, _R_W); y += 28
        dropdown("progress_bar_enabled",
                 ["Ja", "Nein"],
                 "Ja" if cfg.get("progress_bar_enabled", True) else "Nein",
                 x, y, 200); y += 52
        lbl("Ladebalken-Farbe (Hex):", x, y, _R_W); y += 28
        entry("loading_bar_color", cfg.get("loading_bar_color", "#FF6600"), x, y, 200); y += 52

        y += 16  # gap

        # ── BETRIEB ──────────────────────────────────────────────────────
        section_lbl("BETRIEB", x, y, _R_W); y += 42
        lbl("Demo-Modus (Druck simuliert):", x, y, _R_W); y += 28
        dropdown("demo_mode",
                 ["Aus", "Ein"],
                 "Ein" if cfg.get("demo_mode", False) else "Aus",
                 x, y, 200); y += 52
        lbl("Blitz-LED aktiv:", x, y, _R_W); y += 28
        dropdown("flash_enabled",
                 ["Ja", "Nein"],
                 "Ja" if cfg.get("flash_enabled", True) else "Nein",
                 x, y, 200); y += 52
        lbl("CUPS-Druckername:", x, y, _R_W); y += 28
        entry("printer_name", cfg.get("printer_name", "SELPHY"), x, y, _R_ENTRY); y += 52
        lbl("USB-Mount-Pfad:", x, y, _R_W); y += 28
        entry("usb_mount", cfg.get("usb_mount", "/media/usb"), x, y, _R_ENTRY); y += 52

        y += 16  # gap

        # ── GPIO-PINS ────────────────────────────────────────────────────
        section_lbl("GPIO-PINS", x, y, _R_W); y += 42

        pin_pairs = [
            ("pin_start_button", "Start-Button"),
            ("pin_admin_button", "Admin-Button"),
            ("pin_led_flash",    "Flash-LED"),
            ("pin_led_ready",    "Ready-LED"),
        ]
        col_w  = _R_W // 2
        pin_y  = y
        for i, (key, label_text) in enumerate(pin_pairs):
            px = x + (i % 2) * col_w
            py = pin_y + (i // 2) * 76
            lbl(f"{label_text}:", px, py, col_w - _PIN_W - 10);
            entry(f"gpio_{key}", gpio_pins.get(key, 0), px, py + 28, _PIN_W)
        y = pin_y + 2 * 76 + 10

        y += 20

        # ── SAVE BUTTON ──────────────────────────────────────────────────
        save = reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x, y, 280, 50),
            text="Einstellungen speichern", manager=self._mgr,
        ))
        self._fields["save_btn"] = save
        y += 70

        # ── KONFIGURATION ─────────────────────────────────────────────────
        section_lbl("KONFIGURATION", x, y, _R_W); y += 42
        lbl("Einstellungen, Szenen und Pfade sichern:", x, y, _R_W); y += 30
        export_btn = reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x, y, 260, 44),
            text="📤  Exportieren", manager=self._mgr,
        ))
        self._fields["export_btn"] = export_btn
        y += 56

        lbl("Gespeicherte Konfiguration wiederherstellen:", x, y, _R_W); y += 30
        configs      = self._get_available_configs()
        import_dd_w  = _R_W - 200
        import_dd = reg(pygame_gui.elements.UIDropDownMenu(
            options_list=configs, starting_option=configs[0],
            relative_rect=pygame.Rect(x, y, import_dd_w, 44),
            manager=self._mgr,
        ))
        self._fields["import_dd"] = import_dd
        import_btn = reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x + import_dd_w + 10, y + 2, 180, 40),
            text="📥  Importieren", manager=self._mgr,
        ))
        self._fields["import_btn"] = import_btn

    # ------------------------------------------------------------------
    # File dialog
    # ------------------------------------------------------------------

    def _open_dialog(self, target: str):
        if self._file_dialog:
            try: self._file_dialog.kill()
            except Exception: pass
            self._file_dialog = None

        self._file_dialog_target = target

        if target == "bg_file":
            # Type depends on the dropdown selection
            bg_dd = self._fields.get("bg_type")
            is_video = hasattr(bg_dd, "selected_option") and bg_dd.selected_option == "Video-Loop"
            ftype = "video" if is_video else "image"
        elif target.startswith("cover_"):
            ftype = "cover_png"
        else:
            ftype = "image"

        start_dir = _PROJECT_ROOT / _ASSET_DIR.get(ftype, "assets")
        if not start_dir.exists():
            start_dir = _PROJECT_ROOT

        self._file_dialog = open_file_dialog(
            manager=self._mgr,
            initial_path=start_dir,
            extensions=_EXT.get(ftype),
        )

    def _on_file_picked(self, raw_path: str):
        picked = Path(raw_path)
        try:
            rel = str(picked.relative_to(_PROJECT_ROOT))
        except ValueError:
            rel = raw_path

        target = self._file_dialog_target
        if not target:
            return

        if target == "bg_file":
            w = self._fields.get("bg_file")
        elif target.startswith("cover_"):
            w = self._fields.get(target)
        else:
            return

        if w:
            w.set_text(rel)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Config export / import
    # ------------------------------------------------------------------

    def _get_available_configs(self) -> list:
        konfig_dir = _PROJECT_ROOT / "assets" / "konfigurationen"
        if konfig_dir.exists():
            dirs = sorted(d.name for d in konfig_dir.iterdir() if d.is_dir())
        else:
            dirs = []
        return dirs if dirs else ["(keine vorhanden)"]

    def _export_config(self):
        import shutil
        from datetime import datetime
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = _PROJECT_ROOT / "assets" / "konfigurationen" / f"export_{timestamp}"
        export_dir.mkdir(parents=True, exist_ok=True)
        config_dir = _PROJECT_ROOT / "config"
        copied = []
        for fname in ("settings.json", "scenes.json", "paths.json"):
            src = config_dir / fname
            if src.exists():
                shutil.copy2(src, export_dir / fname)
                copied.append(fname)
        if copied:
            self._status_msg = f"Exportiert nach konfigurationen/export_{timestamp}"
            self._status_ok  = True
            import logging
            logging.getLogger(__name__).info("Config exported to %s", export_dir)
        else:
            self._status_msg = "Export fehlgeschlagen – keine Konfigurationsdateien gefunden."
            self._status_ok  = False

    def _import_config(self, config_name: str):
        import shutil
        if config_name in ("(keine vorhanden)", ""):
            self._status_msg = "Keine Konfiguration ausgewählt."
            self._status_ok  = False
            return
        src_dir    = _PROJECT_ROOT / "assets" / "konfigurationen" / config_name
        config_dir = _PROJECT_ROOT / "config"
        if not src_dir.exists():
            self._status_msg = f"Ordner nicht gefunden: {config_name}"
            self._status_ok  = False
            return
        imported = []
        for fname in ("settings.json", "scenes.json", "paths.json"):
            src = src_dir / fname
            if src.exists():
                shutil.copy2(src, config_dir / fname)
                imported.append(fname)
        if not imported:
            self._status_msg = f"Keine Dateien in '{config_name}' gefunden."
            self._status_ok  = False
            return
        # Reload live config and rebuild this panel to reflect new settings
        self.app.config.reload()
        self._status_msg = f"Importiert aus '{config_name}': {', '.join(imported)}"
        self._status_ok  = True
        import logging
        logging.getLogger(__name__).info("Config imported from %s", src_dir)
        # Rebuild panel so all fields show the newly imported values
        self.hide()
        self.show()

    # ------------------------------------------------------------------

    def _save(self):
        self._status_msg = ""
        cfg = self.app.config.settings

        def get_text(key: str, cast=str):
            w = self._fields.get(key)
            if isinstance(w, pygame_gui.elements.UITextEntryLine):
                try:
                    return cast(w.get_text().strip())
                except (ValueError, AttributeError):
                    return None
            return None

        def get_dd(key: str) -> str | None:
            w = self._fields.get(key)
            return getattr(w, "selected_option", None) if w else None

        # Background
        bg_type_sel = get_dd("bg_type")
        cfg["idle_background"] = {
            "type":  "video" if bg_type_sel == "Video-Loop" else "image",
            "file":  get_text("bg_file") or "",
        }

        # Collage covers – validate PNG size
        covers = cfg.setdefault("collage_covers", {})
        errors = []
        for n in range(1, 5):
            path_str = get_text(f"cover_{n}") or ""
            if path_str:
                p = _PROJECT_ROOT / path_str
                if not p.exists():
                    errors.append(f"Overlay {n}: Datei nicht gefunden ({path_str})")
                    continue
                try:
                    img = Image.open(p)
                    if img.size != (COLLAGE_W, COLLAGE_H):
                        errors.append(
                            f"Overlay {n}: Bild ist {img.size[0]}×{img.size[1]} px "
                            f"(erwartet {COLLAGE_W}×{COLLAGE_H} px)"
                        )
                        continue
                except Exception as e:
                    errors.append(f"Overlay {n}: Fehler beim Lesen ({e})")
                    continue
            covers[str(n)] = path_str

        # Display settings
        bar_sel = get_dd("progress_bar_enabled")
        if bar_sel:
            cfg["progress_bar_enabled"] = bar_sel == "Ja"
        cfg["loading_bar_color"] = get_text("loading_bar_color") or "#FF6600"

        # Operation
        demo_sel  = get_dd("demo_mode")
        flash_sel = get_dd("flash_enabled")
        if demo_sel:  cfg["demo_mode"]     = demo_sel  == "Ein"
        if flash_sel: cfg["flash_enabled"] = flash_sel == "Ja"
        cfg["printer_name"] = get_text("printer_name") or "SELPHY"
        cfg["usb_mount"]    = get_text("usb_mount")    or "/media/usb"

        # GPIO pins
        gpio = cfg.setdefault("gpio", {})
        for key in ("pin_start_button", "pin_admin_button", "pin_led_flash", "pin_led_ready"):
            val = get_text(f"gpio_{key}", int)
            if val is not None:
                gpio[key] = val

        self.app.config.save_settings()

        if errors:
            self._status_msg = "Gespeichert – aber: " + " | ".join(errors)
            self._status_ok  = False
        else:
            self._status_msg = "Einstellungen gespeichert."
            self._status_ok  = True
