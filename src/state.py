from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional


class AppState(Enum):
    READY   = "ready"
    INTRO   = "intro"
    CAPTURE = "capture"
    COLLAGE = "collage"
    PRINT   = "print"
    ADMIN   = "admin"


@dataclass
class AppContext:
    state: AppState = AppState.READY
    pre_admin_state: Optional[AppState] = None
    current_path: Optional[dict] = None
    captured_photos: list = field(default_factory=list)
    collage_path: Optional[str] = None

    def start_path(self, path: dict):
        self.current_path = path
        self.captured_photos = []
        self.collage_path = None
        self.state = AppState.INTRO

    def enter_admin(self):
        if self.state != AppState.ADMIN:
            self.pre_admin_state = self.state
            self.state = AppState.ADMIN

    def exit_admin(self):
        self.state = self.pre_admin_state if self.pre_admin_state else AppState.READY
        self.pre_admin_state = None

    def capture_count(self) -> int:
        if not self.current_path:
            return 0
        return self.current_path.get("scenes", {}).get("capture_count", 0)

    def greeting_scene_id(self) -> Optional[str]:
        if not self.current_path:
            return None
        return self.current_path.get("scenes", {}).get("greeting")

    def collage_scene_id(self) -> Optional[str]:
        if not self.current_path:
            return None
        return self.current_path.get("scenes", {}).get("collage")

    def print_scene_id(self) -> Optional[str]:
        if not self.current_path:
            return None
        return self.current_path.get("scenes", {}).get("print")
