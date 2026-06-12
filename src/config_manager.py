"""
Configuration persistence for the Fotobox.

Three JSON files live in config/:
  * settings.json – device/app settings (GPIO pins, sounds, timing, …)
  * scenes.json   – scene definitions (greeting / collage / print media)
  * paths.json    – weighted "paths" combining scenes into a session flow

Missing keys are filled in from the defaults (recursively), so new settings
can be added in code without breaking existing installations. All writes are
atomic (tmp file + rename) so a power loss never corrupts the config.
"""
from __future__ import annotations

import json
import logging
import os
import random
import uuid
from pathlib import Path

from .constants import SCENE_DURATION_DEFAULTS, SCENE_DURATION_RANGES

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
ASSETS_DIR = BASE_DIR / "assets"


def _default_settings() -> dict:
    return {
        "gpio": {
            "pin_start_button": 17,
            "pin_admin_button": 27,
            "pin_gallery_button": 24,
            "pin_led_flash": 22,
            "pin_led_ready": 23,
        },
        "gallery": {
            "enabled": True,
            "background": "",
            "menu_overlay": "",
            "browse_overlay": "",
            "print_background": "",
            "print_overlay": "",
        },
        "collage_covers": {"1": "", "2": "", "3": "", "4": ""},
        "idle_background": {"type": "image", "file": ""},
        "screen_overlays": {
            "start": {"enabled": True, "file": ""},
            "collage": {"enabled": True, "file": ""},
            "print": {"enabled": True, "file": ""},
        },
        "loading_bar_color": "#FF6600",
        "flash_enabled": True,
        "printer_name": "SELPHY",
        "usb_mount": "/media/usb",
        "screen_width": 1920,
        "screen_height": 1080,
        "fullscreen": True,
        "force_headphone_audio": True,
        "system_sounds": {
            "shutter_click": "",
            "countdown_beep": "",
        },
        "capture_timing": {
            "initial_preview_seconds": 2.0,
            "countdown_from": 3,
            "smile_duration": 0.8,
            "smile_enabled": True,
            "post_photo_pause": 2.0,
            "flash_duration": 0.15,
        },
        "smile_overlays": {
            str(n): {"file": "", "enabled": True} for n in range(1, 6)
        },
        "scene_durations": dict(SCENE_DURATION_DEFAULTS),
        "demo_mode": False,
        "progress_bar_enabled": True,
    }


def _merge_defaults(data: dict, defaults: dict) -> dict:
    """Recursively add missing default keys to data (in place)."""
    for key, default_value in defaults.items():
        if key not in data:
            data[key] = default_value
        elif isinstance(default_value, dict) and isinstance(data[key], dict):
            _merge_defaults(data[key], default_value)
    return data


class ConfigManager:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.settings: dict = {}
        self.scenes: dict = {}
        self.paths: dict = {}
        self.reload()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def reload(self):
        """(Re-)read all three config files from disk (e.g. after import)."""
        self.settings = self._load_or_create("settings.json", _default_settings())
        self.scenes = self._load_or_create("scenes.json", {"scenes": []})
        self.paths = self._load_or_create("paths.json", {"paths": []})

    def _load_or_create(self, filename: str, default: dict) -> dict:
        path = CONFIG_DIR / filename
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    logger.debug("Konfiguration geladen: %s", path)
                    return _merge_defaults(data, default)
                logger.warning(
                    "%s hat eine unerwartete Struktur (kein JSON-Objekt) – "
                    "Standardwerte werden verwendet.", filename)
                self._backup_broken(path)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    "%s konnte nicht geladen werden (%s) – Standardwerte "
                    "werden verwendet.", filename, e)
                self._backup_broken(path)
        else:
            logger.info("%s nicht vorhanden – wird mit Standardwerten angelegt.",
                        filename)
        self._save_raw(filename, default)
        return default

    @staticmethod
    def _backup_broken(path: Path):
        """Defekte Config-Datei sichern, bevor sie mit Defaults ersetzt wird."""
        backup = path.with_suffix(path.suffix + ".broken")
        try:
            os.replace(path, backup)
            logger.warning("Defekte Datei gesichert als: %s", backup)
        except OSError as e:
            logger.warning("Defekte Datei %s konnte nicht gesichert werden: %s",
                           path.name, e)

    def _save_raw(self, filename: str, data: dict):
        """Atomic write: never leaves a half-written file behind on power loss."""
        path = CONFIG_DIR / filename
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def save_settings(self):
        self._save_raw("settings.json", self.settings)

    def save_scenes(self):
        self._save_raw("scenes.json", self.scenes)

    def save_paths(self):
        self._save_raw("paths.json", self.paths)

    # ------------------------------------------------------------------
    # Scene helpers
    # ------------------------------------------------------------------

    def get_scenes_by_type(self, scene_type: str) -> list:
        return [s for s in self.scenes["scenes"] if s.get("type") == scene_type]

    def get_scene_by_id(self, scene_id: str) -> dict | None:
        for s in self.scenes["scenes"]:
            if s.get("id") == scene_id:
                return s
        return None

    def add_scene(self, scene: dict) -> str:
        scene_id = str(uuid.uuid4())[:8]
        scene["id"] = scene_id
        self.scenes["scenes"].append(scene)
        self.save_scenes()
        return scene_id

    def update_scene(self, scene_id: str, updated: dict) -> bool:
        for i, s in enumerate(self.scenes["scenes"]):
            if s.get("id") == scene_id:
                updated["id"] = scene_id
                self.scenes["scenes"][i] = updated
                self.save_scenes()
                return True
        return False

    def delete_scene(self, scene_id: str) -> list[str]:
        """Delete scene and all paths that reference it. Returns deleted path IDs."""
        self.scenes["scenes"] = [s for s in self.scenes["scenes"] if s.get("id") != scene_id]
        self.save_scenes()
        return self._remove_paths_using_scene(scene_id)

    def paths_using_scene(self, scene_id: str) -> list:
        result = []
        for p in self.paths["paths"]:
            scenes = p.get("scenes", {})
            if scene_id in (scenes.get("greeting"), scenes.get("collage"), scenes.get("print")):
                result.append(p)
        return result

    def _remove_paths_using_scene(self, scene_id: str) -> list[str]:
        to_delete = [p["id"] for p in self.paths_using_scene(scene_id)]
        if to_delete:
            self.paths["paths"] = [p for p in self.paths["paths"] if p["id"] not in to_delete]
            self.save_paths()
        return to_delete

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def get_paths(self) -> list:
        return self.paths["paths"]

    def get_default_path(self) -> dict | None:
        paths = self.paths["paths"]
        if not paths:
            return None
        for p in paths:
            if p.get("is_default"):
                return p
        return paths[0]

    def add_path(self, path: dict) -> str:
        path_id = str(uuid.uuid4())[:8]
        path["id"] = path_id
        if not self.paths["paths"]:
            path["is_default"] = True
        self.paths["paths"].append(path)
        self.save_paths()
        return path_id

    def update_path(self, path_id: str, updated: dict) -> bool:
        for i, p in enumerate(self.paths["paths"]):
            if p.get("id") == path_id:
                updated["id"] = path_id
                self.paths["paths"][i] = updated
                self.save_paths()
                return True
        return False

    def delete_path(self, path_id: str):
        self.paths["paths"] = [p for p in self.paths["paths"] if p.get("id") != path_id]
        if self.paths["paths"] and not any(p.get("is_default") for p in self.paths["paths"]):
            self.paths["paths"][0]["is_default"] = True
        self.save_paths()

    def compute_default_probability(self) -> int:
        """Return the remaining probability assigned to the default path."""
        other_sum = sum(
            p.get("probability", 0)
            for p in self.paths["paths"]
            if not p.get("is_default")
        )
        return max(0, 100 - other_sum)

    def select_random_path(self) -> dict | None:
        paths = self.paths["paths"]
        if not paths:
            return None
        weights = [
            self.compute_default_probability() if p.get("is_default")
            else p.get("probability", 0)
            for p in paths
        ]
        if sum(weights) == 0:
            return paths[0]
        return random.choices(paths, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # Scene durations (admin-configurable, see constants.SCENE_DURATION_RANGES)
    # ------------------------------------------------------------------

    def scene_durations(self) -> dict:
        """Configured scene durations, clamped to the allowed value ranges."""
        raw = self.settings.get("scene_durations", {})
        out = {}
        for key, (lo, hi) in SCENE_DURATION_RANGES.items():
            try:
                value = float(raw.get(key, SCENE_DURATION_DEFAULTS[key]))
            except (TypeError, ValueError):
                value = float(SCENE_DURATION_DEFAULTS[key])
            out[key] = min(float(hi), max(float(lo), value))
        return out

    def scene_duration_limits(self, scene_type: str) -> tuple[float, float]:
        """Allowed media duration (lo, hi) for a scene type.

        Greeting media must fill at least the configured minimum; collage and
        print audio may be any length up to the fixed screen duration.
        """
        d = self.scene_durations()
        if scene_type == "greeting":
            return d["greeting_min"], d["greeting_max"]
        return 0.0, d[scene_type]

    def scenes_violating_durations(self, durations: dict) -> list[str]:
        """Names of scenes that do not fit the given duration settings.

        Collage/print video scenes are always violations (no longer supported).
        """
        bad = []
        for s in self.scenes["scenes"]:
            stype = s.get("type")
            dur = float(s.get("duration", 0))
            if stype == "greeting":
                ok = durations["greeting_min"] <= dur <= durations["greeting_max"]
            elif stype in ("collage", "print"):
                ok = s.get("media_type", "photo") == "photo" and dur <= durations[stype]
            else:
                ok = True
            if not ok:
                bad.append(s.get("name") or s.get("id", "?"))
        return bad

    # ------------------------------------------------------------------
    # Gallery
    # ------------------------------------------------------------------

    def gallery_background(self, key: str = "background") -> str:
        return self.settings.get("gallery", {}).get(key, "")

    def gallery_enabled(self) -> bool:
        """False = the gallery (and its button) is switched off entirely."""
        return bool(self.settings.get("gallery", {}).get("enabled", True))

    # ------------------------------------------------------------------
    # Smile overlays (capture screen)
    # ------------------------------------------------------------------

    def smile_overlay_files(self) -> list[str]:
        """Files of all enabled, non-empty smile overlay slots (1–5)."""
        slots = self.settings.get("smile_overlays", {})
        return [ov["file"] for n in range(1, 6)
                if (ov := slots.get(str(n), {})).get("file")
                and ov.get("enabled", True)]

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def loading_bar_color_rgb(self) -> tuple:
        hex_color = self.settings.get("loading_bar_color", "#FF6600").lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def gpio_pins(self) -> dict:
        return self.settings.get("gpio", {})

    def usb_path(self, subdir: str = "") -> Path:
        base = Path(self.settings.get("usb_mount", "/media/usb"))
        return base / subdir if subdir else base

    def cover_path(self, count: int) -> str:
        return self.settings.get("collage_covers", {}).get(str(count), "")

    def resolve_asset(self, relative_path: str) -> Path:
        """Resolve a path relative to the project root (absolute paths pass through)."""
        if not relative_path:
            return Path()
        p = Path(relative_path)
        return p if p.is_absolute() else BASE_DIR / p
