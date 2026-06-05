"""
Admin Settings tab – tabbed layout grouped by category.

Tabs:
  Startscreen  – idle background (image / video loop)
  Overlays     – PNG collage covers (1–4 photos)
  Darstellung  – progress bar visibility + colour
  Gerät        – demo mode, flash LED, printer, USB, GPIO pins
  Sicherung    – export config (with custom name) + import
"""
from __future__ import annotations
from pathlib import Path

import pygame
import pygame_gui
from PIL import Image

from ...constants import SCREEN_W, SCREEN_H, ADMIN_PANEL, COLLAGE_W, COLLAGE_H
from ..base_screen import get_font
from .file_dialog import open_file_dialog

_PROJECT_ROOT = Path(__file__).parents[3]

_TOP    = 70
_MARGIN = 20
_W      = SCREEN_W - 2 * _MARGIN
_H      = SCREEN_H - _TOP - _MARGIN

# ── Tab bar ────────────────────────────────────────────────────────────
_TABS = ["Startscreen", "Overlays", "Darstellung", "Gerät", "Sicherung"]
_TAB_H  = 40
_TAB_Y  = _TOP + 6
_TAB_W  = (_W - (_MARGIN + 10) * 2) // len(_TABS) - 4
_CONT_Y = _TAB_Y + _TAB_H + 8   # content area top
_CONT_X = _MARGIN + 10
_CONT_W = _W - 20
_SAVE_Y = SCREEN_H - 65          # global save button

# ── Field widths ───────────────────────────────────────────────────────
_BROWSE_W = 110
_ENTRY_W  = 600
_ENTRY_WITH_BROWSE = _ENTRY_W - _BROWSE_W - 10
_PIN_W    = 80

# ── Allowed file extensions ────────────────────────────────────────────
_EXT = {
    "image":     {".jpg", ".jpeg", ".png"},
    "video":     {".mp4", ".avi", ".mov"},
    "cover_png": {".png"},
}
_ASSET_DIR = {
    "image":     "assets/backgrounds",
    "video":     "assets/backgrounds",
    "cover_png": "assets/CollageCovers",
}


class AdminSettings:
    def __init__(self, app, manager: pygame_gui.UIManager):
        self.app      = app
        self._mgr     = manager
        self._active  = False
        self._widgets: list = []
        self._fields:  dict = {}

        # Per-tab widget lists (for show/hide on tab switch)
        self._tab_content: dict = {t: [] for t in _TABS}
        self._tab_btns:    dict = {}
        self._active_tab   = _TABS[0]

        self._status_msg = ""
        self._status_ok  = True

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

        if event.type == pygame_gui.UI_FILE_DIALOG_PATH_PICKED:
            self._on_file_picked(event.text)
            self._file_dialog = None
            self._file_dialog_target = None
            return

        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if event.ui_element == self._fields.get("bg_type"):
                is_video = event.text == "Video-Loop"
                hint = self._fields.get("bg_file_hint")
                if hint:
                    hint.set_text("Videodatei (.mp4):" if is_video else "Bilddatei (.jpg / .png):")
            return

        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return
        el = event.ui_element

        # Tab switching
        for tab_name, btn in self._tab_btns.items():
            if el == btn:
                self._switch_tab(tab_name)
                return

        # Save all settings
        if el == self._fields.get("save_btn"):
            self._save(); return

        # Export
        if el == self._fields.get("export_btn"):
            self._export_config(); return

        # Import
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
        pygame.draw.rect(surface, ADMIN_PANEL,
                         (_MARGIN, _TAB_Y - 4, _W, _H - _TAB_Y + _TOP + 4), border_radius=8)
        if self._status_msg:
            color = (80, 210, 100) if self._status_ok else (220, 60, 60)
            surf  = get_font(22).render(self._status_msg, True, color)
            surface.blit(surf, (_CONT_X, SCREEN_H - 50))

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    def _switch_tab(self, tab_name: str):
        if tab_name == self._active_tab:
            return
        for w in self._tab_content.get(self._active_tab, []):
            try: w.hide()
            except Exception: pass
        self._active_tab = tab_name
        for w in self._tab_content.get(self._active_tab, []):
            try: w.show()
            except Exception: pass

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _kill_all(self):
        for w in self._widgets:
            try: w.kill()
            except Exception: pass
        self._widgets.clear()
        self._fields.clear()
        for k in _TABS:
            self._tab_content[k] = []
        self._tab_btns.clear()
        if self._file_dialog:
            try: self._file_dialog.kill()
            except Exception: pass
            self._file_dialog = None

    def _reg(self, w, tab: str | None = None):
        """Register a widget, optionally into a tab's content list."""
        self._widgets.append(w)
        if tab:
            self._tab_content[tab].append(w)
        return w

    def _build(self):
        self._kill_all()
        cfg = self.app.config.settings

        # ── Tab buttons ────────────────────────────────────────────────
        for i, tab in enumerate(_TABS):
            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(
                    _CONT_X + i * (_TAB_W + 4), _TAB_Y, _TAB_W, _TAB_H
                ),
                text=tab, manager=self._mgr,
            )
            self._reg(btn)
            self._tab_btns[tab] = btn

        # ── Global save button (always visible) ────────────────────────
        save_btn = self._reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(_CONT_X, _SAVE_Y, 300, 46),
            text="Einstellungen speichern", manager=self._mgr,
        ))
        self._fields["save_btn"] = save_btn

        # ── Tab content ────────────────────────────────────────────────
        self._build_startscreen(cfg)
        self._build_overlays(cfg)
        self._build_darstellung(cfg)
        self._build_geraet(cfg)
        self._build_sicherung()

        # Hide all tabs except the active one
        for tab in _TABS:
            if tab != self._active_tab:
                for w in self._tab_content[tab]:
                    try: w.hide()
                    except Exception: pass

    # ── helpers shared by tab builders ────────────────────────────────

    def _lbl(self, text: str, x: int, y: int, tab: str, width: int = 560, height: int = 28):
        return self._reg(pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x, y, width, height),
            text=text, manager=self._mgr,
        ), tab)

    def _entry(self, key: str, value, x: int, y: int, tab: str, width: int = _ENTRY_W):
        e = self._reg(pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(x, y, width, 40),
            manager=self._mgr,
        ), tab)
        e.set_text(str(value))
        self._fields[key] = e
        return e

    def _entry_browse(self, entry_key: str, browse_key: str, value: str,
                      x: int, y: int, tab: str):
        e = self._reg(pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(x, y, _ENTRY_WITH_BROWSE, 40),
            manager=self._mgr,
        ), tab)
        e.set_text(str(value))
        self._fields[entry_key] = e
        btn = self._reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x + _ENTRY_WITH_BROWSE + 10, y, _BROWSE_W, 40),
            text="📂 Suchen", manager=self._mgr,
        ), tab)
        self._fields[f"browse_{browse_key}"] = btn
        return e, btn

    def _dropdown(self, key: str, options: list, selected: str,
                  x: int, y: int, tab: str, width: int = 220):
        if selected not in options:
            selected = options[0]
        dd = self._reg(pygame_gui.elements.UIDropDownMenu(
            options_list=options, starting_option=selected,
            relative_rect=pygame.Rect(x, y, width, 44),
            manager=self._mgr,
        ), tab)
        self._fields[key] = dd
        return dd

    # ------------------------------------------------------------------
    # Tab: Startscreen
    # ------------------------------------------------------------------

    def _build_startscreen(self, cfg: dict):
        tab    = "Startscreen"
        idle   = cfg.get("idle_background", {})
        x, y   = _CONT_X, _CONT_Y

        self._lbl("Hintergrundtyp:", x, y, tab, _ENTRY_W); y += 30
        bg_type_val = "Video-Loop" if idle.get("type") == "video" else "Bild (statisch)"
        self._dropdown("bg_type", ["Bild (statisch)", "Video-Loop"], bg_type_val, x, y, tab, 280)
        y += 52

        is_video   = idle.get("type") == "video"
        hint_text  = "Videodatei (.mp4):" if is_video else "Bilddatei (.jpg / .png):"
        hint = self._reg(pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x, y, _ENTRY_W, 28),
            text=hint_text, manager=self._mgr,
        ), tab)
        self._fields["bg_file_hint"] = hint; y += 30
        self._entry_browse("bg_file", "bg_file", idle.get("file", ""), x, y, tab); y += 52

    # ------------------------------------------------------------------
    # Tab: Overlays
    # ------------------------------------------------------------------

    def _build_overlays(self, cfg: dict):
        tab    = "Overlays"
        covers = cfg.get("collage_covers", {})
        x, y   = _CONT_X, _CONT_Y

        self._lbl("Collage-Overlays (PNG, 1800×1200 px) – ein Cover pro Foto-Anzahl:",
                  x, y, tab, _CONT_W); y += 34

        for n in range(1, 5):
            plural = "Foto" if n == 1 else "Fotos"
            self._lbl(f"{n} {plural}:", x, y, tab, _ENTRY_W); y += 28
            self._entry_browse(f"cover_{n}", f"cover_{n}", covers.get(str(n), ""), x, y, tab)
            y += 50

    # ------------------------------------------------------------------
    # Tab: Darstellung
    # ------------------------------------------------------------------

    def _build_darstellung(self, cfg: dict):
        tab  = "Darstellung"
        x, y = _CONT_X, _CONT_Y

        self._lbl("Ladebalken anzeigen:", x, y, tab, 360); y += 30
        self._dropdown("progress_bar_enabled",
                       ["Ja", "Nein"],
                       "Ja" if cfg.get("progress_bar_enabled", True) else "Nein",
                       x, y, tab, 200)
        y += 52
        self._lbl("Ladebalken-Farbe (Hex, z. B. #FF6600):", x, y, tab, 400); y += 30
        self._entry("loading_bar_color", cfg.get("loading_bar_color", "#FF6600"),
                    x, y, tab, 200)

    # ------------------------------------------------------------------
    # Tab: Gerät
    # ------------------------------------------------------------------

    def _build_geraet(self, cfg: dict):
        tab      = "Gerät"
        gpio     = cfg.get("gpio", {})
        x, y     = _CONT_X, _CONT_Y
        col2_x   = x + 640

        # Left side: demo, flash, printer, USB
        self._lbl("Demo-Modus (Druck simuliert):", x, y, tab, 580); y += 30
        self._dropdown("demo_mode", ["Aus", "Ein"],
                       "Ein" if cfg.get("demo_mode", False) else "Aus",
                       x, y, tab, 200); y += 52

        self._lbl("Blitz-LED aktiv:", x, y, tab, 580); y += 30
        self._dropdown("flash_enabled", ["Ja", "Nein"],
                       "Ja" if cfg.get("flash_enabled", True) else "Nein",
                       x, y, tab, 200); y += 52

        self._lbl("CUPS-Druckername:", x, y, tab, 580); y += 30
        self._entry("printer_name", cfg.get("printer_name", "SELPHY"), x, y, tab, 320); y += 52

        self._lbl("USB-Mount-Pfad:", x, y, tab, 580); y += 30
        self._entry("usb_mount", cfg.get("usb_mount", "/media/usb"), x, y, tab, 380)

        # Right side: GPIO pins (2×2 grid)
        gy = _CONT_Y
        pin_pairs = [
            ("pin_start_button", "Start-Button"),
            ("pin_admin_button", "Admin-Button"),
            ("pin_led_flash",    "Flash-LED"),
            ("pin_led_ready",    "Ready-LED"),
        ]
        self._lbl("GPIO-Pins:", col2_x, gy, tab, 400); gy += 34
        col_w = 280
        for i, (key, label_text) in enumerate(pin_pairs):
            px = col2_x + (i % 2) * col_w
            py = gy + (i // 2) * 72
            self._lbl(f"{label_text}:", px, py, tab, col_w - _PIN_W - 10)
            self._entry(f"gpio_{key}", gpio.get(key, 0), px, py + 28, tab, _PIN_W)

    # ------------------------------------------------------------------
    # Tab: Sicherung
    # ------------------------------------------------------------------

    def _build_sicherung(self):
        tab  = "Sicherung"
        x, y = _CONT_X, _CONT_Y

        # Export section
        self._lbl("Konfiguration sichern (Einstellungen + Szenen + Pfade):",
                  x, y, tab, _CONT_W); y += 34
        self._lbl("Name für den Export:", x, y, tab, 300); y += 30
        self._entry("export_name", "", x, y, tab, 440); y += 52
        export_btn = self._reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x, y, 220, 44),
            text="📤  Exportieren", manager=self._mgr,
        ), tab)
        self._fields["export_btn"] = export_btn; y += 70

        # Import section
        self._lbl("Gespeicherte Konfiguration wiederherstellen:", x, y, tab, _CONT_W); y += 34
        configs    = self._get_available_configs()
        dd_w       = min(500, _CONT_W - 220)
        import_dd  = self._reg(pygame_gui.elements.UIDropDownMenu(
            options_list=configs, starting_option=configs[0],
            relative_rect=pygame.Rect(x, y, dd_w, 44),
            manager=self._mgr,
        ), tab)
        self._fields["import_dd"] = import_dd
        import_btn = self._reg(pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x + dd_w + 10, y + 2, 200, 40),
            text="📥  Importieren", manager=self._mgr,
        ), tab)
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
            bg_dd    = self._fields.get("bg_type")
            is_video = hasattr(bg_dd, "selected_option") and bg_dd.selected_option == "Video-Loop"
            ftype    = "video" if is_video else "image"
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

        # Use custom name from text entry, fall back to timestamp
        name_entry = self._fields.get("export_name")
        custom_name = ""
        if isinstance(name_entry, pygame_gui.elements.UITextEntryLine):
            raw = name_entry.get_text().strip()
            # Sanitise: remove characters invalid in directory names
            custom_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in raw)

        folder_name = custom_name or datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir  = _PROJECT_ROOT / "assets" / "konfigurationen" / folder_name
        export_dir.mkdir(parents=True, exist_ok=True)

        config_dir = _PROJECT_ROOT / "config"
        copied = []
        for fname in ("settings.json", "scenes.json", "paths.json"):
            src = config_dir / fname
            if src.exists():
                shutil.copy2(src, export_dir / fname)
                copied.append(fname)

        if copied:
            self._status_msg = f"Exportiert als '{folder_name}'"
            self._status_ok  = True
            import logging
            logging.getLogger(__name__).info("Config exported to %s", export_dir)
        else:
            self._status_msg = "Export fehlgeschlagen – keine Konfigurationsdateien gefunden."
            self._status_ok  = False

        # Rebuild Sicherung tab so the import dropdown shows the new entry
        for w in self._tab_content.get("Sicherung", []):
            try: w.kill()
            except Exception: pass
        self._tab_content["Sicherung"] = []
        for key in ("export_btn", "import_dd", "import_btn", "export_name"):
            self._fields.pop(key, None)
        self._build_sicherung()
        if self._active_tab != "Sicherung":
            for w in self._tab_content["Sicherung"]:
                try: w.hide()
                except Exception: pass

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

        self.app.config.reload()
        self._status_msg = f"Importiert: '{config_name}'"
        self._status_ok  = True
        import logging
        logging.getLogger(__name__).info("Config imported from %s", src_dir)

        # Rebuild the whole panel to reflect new settings
        self.hide()
        self.show()

    # ------------------------------------------------------------------
    # Save
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
            "type": "video" if bg_type_sel == "Video-Loop" else "image",
            "file": get_text("bg_file") or "",
        }

        # Collage covers – validate PNG size and existence
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
        if bar_sel is not None:
            cfg["progress_bar_enabled"] = bar_sel == "Ja"
        cfg["loading_bar_color"] = get_text("loading_bar_color") or "#FF6600"

        # Operation
        demo_sel  = get_dd("demo_mode")
        flash_sel = get_dd("flash_enabled")
        if demo_sel  is not None: cfg["demo_mode"]     = demo_sel  == "Ein"
        if flash_sel is not None: cfg["flash_enabled"] = flash_sel == "Ja"
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
