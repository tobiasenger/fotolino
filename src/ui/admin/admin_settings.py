"""
Admin Settings tab.
Upload collage covers, idle background, loading bar color,
GPIO pins, flash toggle, printer name, USB mount path.
"""
from __future__ import annotations
import shutil
from pathlib import Path

import pygame
import pygame_gui
from PIL import Image

from ...constants import (
    SCREEN_W, SCREEN_H, ADMIN_BG, ADMIN_PANEL,
    COLOR_TEXT, COLOR_ACCENT, COLOR_SUCCESS, COLOR_ERROR,
    COLLAGE_W, COLLAGE_H,
)
from ..base_screen import get_font

_TOP    = 70
_MARGIN = 20
_W      = SCREEN_W - 2 * _MARGIN
_H      = SCREEN_H - _TOP - _MARGIN

_COL1 = _MARGIN + 10
_COL2 = _MARGIN + 500


class AdminSettings:
    def __init__(self, app, manager: pygame_gui.UIManager):
        self.app    = app
        self._mgr   = manager
        self._active = False
        self._widgets: list = []
        self._status_msg  = ""
        self._status_ok   = True
        self._fields: dict = {}   # key -> UITextEntryLine or UIButton

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
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            el = event.ui_element
            for key, widget in self._fields.items():
                if el == widget and key.startswith("upload_"):
                    self._handle_upload(key)
                    return
            if el == self._fields.get("save_btn"):
                self._save()
                return
        if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            pass  # flash toggle

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        if not self._active:
            return
        pygame.draw.rect(surface, ADMIN_PANEL,
                         (_MARGIN, _TOP, _W, _H), border_radius=8)
        if self._status_msg:
            color = COLOR_SUCCESS if self._status_ok else COLOR_ERROR
            font = get_font(24)
            surf = font.render(self._status_msg, True, color)
            surface.blit(surf, (_MARGIN + 20, SCREEN_H - 55))

    # ------------------------------------------------------------------

    def _kill_all(self):
        for w in self._widgets:
            try: w.kill()
            except Exception: pass
        self._widgets.clear()
        self._fields.clear()

    def _build(self):
        self._kill_all()
        cfg = self.app.config.settings
        x1, x2 = _COL1, _COL2
        y = _TOP + 20

        def lbl(text, x, yy, width=460):
            lb = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(x, yy, width, 28),
                text=text, manager=self._mgr,
            )
            self._widgets.append(lb)

        def entry(key, value, x, yy, width=440):
            e = pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(x, yy, width, 40),
                manager=self._mgr,
            )
            e.set_text(str(value))
            self._widgets.append(e)
            self._fields[key] = e
            return e

        def upload_btn(key, label_text, x, yy, width=440):
            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(x, yy, width, 40),
                text=label_text, manager=self._mgr,
            )
            self._widgets.append(btn)
            self._fields[key] = btn
            return btn

        # ---- Left column ----
        lbl("Collage-Overlays (PNG, 1800×1200 px):", x1, y); y += 30
        for n in range(1, 5):
            cur = cfg.get("collage_covers", {}).get(str(n), "") or "(nicht gesetzt)"
            short = Path(cur).name if cur != "(nicht gesetzt)" else cur
            upload_btn(f"upload_cover_{n}", f"{n} Foto(s): {short}", x1, y, 440); y += 48

        y += 10
        lbl("Startscreen-Hintergrund:", x1, y); y += 30
        cur_bg = cfg.get("idle_background", {}).get("file", "") or "(nicht gesetzt)"
        upload_btn("upload_bg", f"Datei: {Path(cur_bg).name if cur_bg != '(nicht gesetzt)' else cur_bg}", x1, y, 440); y += 48

        y += 10
        lbl("Ladebalken-Farbe (Hex, z.B. #FF6600):", x1, y); y += 30
        entry("loading_bar_color", cfg.get("loading_bar_color", "#FF6600"), x1, y, 200); y += 50

        lbl("Blitz-LED aktiv:", x1, y); y += 30
        flash_opts = ["Ja", "Nein"]
        flash_sel  = "Ja" if cfg.get("flash_enabled", True) else "Nein"
        dd_flash = pygame_gui.elements.UIDropDownMenu(
            options_list=flash_opts, starting_option=flash_sel,
            relative_rect=pygame.Rect(x1, y, 200, 44), manager=self._mgr,
        )
        self._widgets.append(dd_flash)
        self._fields["flash_enabled"] = dd_flash
        y += 54

        lbl("Demo-Modus (kein Drucker nötig):", x1, y); y += 30
        demo_opts = ["Aus", "Ein"]
        demo_sel  = "Ein" if cfg.get("demo_mode", False) else "Aus"
        dd_demo = pygame_gui.elements.UIDropDownMenu(
            options_list=demo_opts, starting_option=demo_sel,
            relative_rect=pygame.Rect(x1, y, 200, 44), manager=self._mgr,
        )
        demo_info = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(x1 + 210, y + 6, 240, 32),
            text="(Druck wird nur simuliert)", manager=self._mgr,
        )
        self._widgets += [dd_demo, demo_info]
        self._fields["demo_mode"] = dd_demo
        y += 54

        # ---- Right column ----
        yr = _TOP + 20
        lbl("GPIO-Pins:", x2, yr); yr += 30
        pins = cfg.get("gpio", {})
        for key, label in [
            ("pin_start_button", "Start-Button"),
            ("pin_admin_button", "Admin-Button"),
            ("pin_led_flash",    "Flash-LED"),
            ("pin_led_ready",    "Ready-LED"),
        ]:
            lbl(f"{label}:", x2, yr, 200); yr += 28
            entry(f"gpio_{key}", pins.get(key, 0), x2, yr, 120); yr += 48

        yr += 10
        lbl("CUPS-Druckername:", x2, yr); yr += 30
        entry("printer_name", cfg.get("printer_name", "SELPHY"), x2, yr, 300); yr += 50

        lbl("USB-Mount-Pfad:", x2, yr); yr += 30
        entry("usb_mount", cfg.get("usb_mount", "/media/usb"), x2, yr, 300); yr += 50

        # Save button
        save = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(x2, yr + 10, 200, 48),
            text="Einstellungen speichern", manager=self._mgr,
        )
        self._widgets.append(save)
        self._fields["save_btn"] = save

    def _save(self):
        cfg = self.app.config.settings

        def get_entry(key, cast=str):
            w = self._fields.get(key)
            if isinstance(w, pygame_gui.elements.UITextEntryLine):
                try:
                    return cast(w.get_text().strip())
                except (ValueError, AttributeError):
                    return None
            return None

        cfg["loading_bar_color"] = get_entry("loading_bar_color") or "#FF6600"
        cfg["printer_name"]      = get_entry("printer_name") or "SELPHY"
        cfg["usb_mount"]         = get_entry("usb_mount")    or "/media/usb"

        flash_dd = self._fields.get("flash_enabled")
        if hasattr(flash_dd, "selected_option"):
            cfg["flash_enabled"] = flash_dd.selected_option == "Ja"

        demo_dd = self._fields.get("demo_mode")
        if hasattr(demo_dd, "selected_option"):
            cfg["demo_mode"] = demo_dd.selected_option == "Ein"

        pins = cfg.setdefault("gpio", {})
        for key in ("pin_start_button", "pin_admin_button", "pin_led_flash", "pin_led_ready"):
            val = get_entry(f"gpio_{key}", int)
            if val is not None:
                pins[key] = val

        self.app.config.save_settings()
        self._status_msg = "Einstellungen gespeichert."
        self._status_ok  = True

    def _handle_upload(self, key: str):
        """
        For demo purposes we show how to copy a file.
        In production this would open a file picker dialog.
        The user copies files to assets/ directly, then enters the path as text.
        """
        # Derive the field that holds the current path
        # (upload buttons trigger copy; path is typed in an adjacent text entry)
        # For now: nothing to do – just show a hint.
        self._status_msg = "Datei bitte manuell nach assets/ kopieren und Pfad eingeben."
        self._status_ok  = False

    def _copy_and_validate_cover(self, src: str, count: int) -> bool:
        """Validate a PNG cover (1800×1200) and copy it to assets/CollageCovers/."""
        p = Path(src)
        if not p.exists():
            return False
        try:
            img = Image.open(p)
            if img.size != (COLLAGE_W, COLLAGE_H):
                self._status_msg = f"Fehler: Overlay muss {COLLAGE_W}×{COLLAGE_H} px sein."
                self._status_ok  = False
                return False
            dest_dir = self.app.config.resolve_asset("assets/CollageCovers")
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"cover_{count}.png"
            shutil.copy2(p, dest)
            rel = str(dest.relative_to(self.app.config.resolve_asset("")))
            self.app.config.settings.setdefault("collage_covers", {})[str(count)] = rel
            self.app.config.save_settings()
            self._status_msg = f"Cover {count} gespeichert."
            self._status_ok  = True
            return True
        except Exception as e:
            self._status_msg = f"Fehler: {e}"
            self._status_ok  = False
            return False
