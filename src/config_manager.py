import json
import random
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
ASSETS_DIR = BASE_DIR / "assets"


def _default_settings():
    return {
        "gpio": {
            "pin_start_button": 17,
            "pin_admin_button": 27,
            "pin_led_flash": 22,
            "pin_led_ready": 23,
        },
        "collage_covers": {"1": "", "2": "", "3": "", "4": ""},
        "idle_background": {"type": "image", "file": ""},
        "loading_bar_color": "#FF6600",
        "flash_enabled": True,
        "printer_name": "SELPHY",
        "usb_mount": "/media/usb",
        "screen_width": 1920,
        "screen_height": 1080,
        "fullscreen": True,
        "system_sounds": {
            "shutter_click": "assets/sounds/click.mp3",
            "countdown_beep": "",
        },
        "capture_timing": {
            "initial_preview_seconds": 2.0,
            "countdown_from": 3,
            "smile_duration": 0.8,
            "post_photo_pause": 2.0,
            "flash_duration": 0.15,
        },
        "demo_mode": False,
        "progress_bar_enabled": True,
    }


class ConfigManager:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = self._load_or_create("settings.json", _default_settings())
        self.scenes   = self._load_or_create("scenes.json",   {"scenes": []})
        self.paths    = self._load_or_create("paths.json",    {"paths": []})

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load_or_create(self, filename, default):
        path = CONFIG_DIR / filename
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load %s (%s), using defaults", filename, e)
        self._save_raw(filename, default)
        return default

    def _save_raw(self, filename, data):
        path = CONFIG_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

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

    def update_scene(self, scene_id: str, updated: dict):
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
            if scenes.get("greeting") == scene_id or \
               scenes.get("collage")  == scene_id or \
               scenes.get("print")    == scene_id:
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

    def update_path(self, path_id: str, updated: dict):
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
        weights = []
        for p in paths:
            if p.get("is_default"):
                weights.append(self.compute_default_probability())
            else:
                weights.append(p.get("probability", 0))
        if sum(weights) == 0:
            return paths[0]
        return random.choices(paths, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def loading_bar_color_rgb(self) -> tuple:
        hex_color = self.settings.get("loading_bar_color", "#FF6600").lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def gpio_pins(self) -> dict:
        return self.settings.get("gpio", {})

    def usb_path(self, subdir: str = "") -> Path:
        base = Path(self.settings.get("usb_mount", "/media/usb"))
        return base / subdir if subdir else base

    def cover_path(self, count: int) -> str:
        return self.settings.get("collage_covers", {}).get(str(count), "")

    def reload(self):
        """Re-read all three config files from disk (e.g. after import)."""
        self.settings = self._load_or_create("settings.json", _default_settings())
        self.scenes   = self._load_or_create("scenes.json",   {"scenes": []})
        self.paths    = self._load_or_create("paths.json",    {"paths": []})

    def resolve_asset(self, relative_path: str) -> Path:
        """Resolve a path relative to project root."""
        if not relative_path:
            return Path()
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return BASE_DIR / p
