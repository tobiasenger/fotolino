from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class AppState(Enum):
    READY   = "ready"
    INTRO   = "intro"
    CAPTURE = "capture"
    COLLAGE = "collage"
    PRINT   = "print"
    SEGMENT = "segment"
    GALLERY = "gallery"
    ADMIN   = "admin"


@dataclass
class AppContext:
    state: AppState = AppState.READY
    pre_admin_state: Optional[AppState] = None
    current_path: Optional[dict] = None
    captured_photos: list = field(default_factory=list)
    collage_path: Optional[str] = None
    # Custom paths: index of the running segment and whether a collage of a
    # finished capture segment is still being built in the background.
    segment_index: int = 0
    collage_pending: bool = False

    def start_path(self, path: dict):
        self.current_path = path
        self.captured_photos = []
        self.collage_path = None
        self.segment_index = 0
        self.collage_pending = False

    def end_session(self):
        """Drop all per-session data (finished or aborted run)."""
        self.current_path = None
        self.captured_photos = []
        self.collage_path = None
        self.segment_index = 0
        self.collage_pending = False

    def enter_admin(self):
        if self.state != AppState.ADMIN:
            self.pre_admin_state = self.state
            self.state = AppState.ADMIN

    def exit_admin(self):
        self.state = self.pre_admin_state if self.pre_admin_state else AppState.READY
        self.pre_admin_state = None

    # ------------------------------------------------------------------
    # Custom paths (segment sequence)
    # ------------------------------------------------------------------

    def is_custom_path(self) -> bool:
        return bool(self.current_path) and self.current_path.get("type") == "custom"

    def segments(self) -> list:
        if not self.current_path:
            return []
        return self.current_path.get("segments", [])

    def current_segment(self) -> Optional[dict]:
        segments = self.segments()
        if 0 <= self.segment_index < len(segments):
            return segments[self.segment_index]
        return None

    # ------------------------------------------------------------------
    # Standard paths (scene references) – also feed the capture screen
    # ------------------------------------------------------------------

    def capture_count(self) -> int:
        if not self.current_path:
            return 0
        if self.is_custom_path():
            segment = self.current_segment() or {}
            if segment.get("type") != "capture":
                return 0
            try:
                return int(segment.get("capture_count", 0))
            except (TypeError, ValueError):
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
