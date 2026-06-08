"""
Intro / greeting screen – plays the greeting scene (image+audio or video).
Auto-advances after the scene duration.

Video playback strategy:
  1. mpv subprocess (hardware H.264 decoding via --hwdec=auto on Pi 4)
  2. Threaded cv2 fallback if mpv is not installed
"""
import logging
import queue
import subprocess
import threading
from pathlib import Path

import pygame

logger = logging.getLogger(__name__)

from .base_screen import BaseScreen, draw_text_centered, get_font
from ..constants import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_TEXT,
    SCREEN_TRANSITION, FONT_MEDIUM, SCENE_GREETING_MAX,
)

try:
    import cv2
    import numpy as np
    _CV2 = True
except ImportError:
    _CV2 = False


class IntroScreen(BaseScreen):
    def __init__(self, app):
        super().__init__(app)
        self._scene: dict | None = None
        self._elapsed  = 0.0
        self._duration = 5.0
        self._bg_surface: pygame.Surface | None = None
        # mpv subprocess (primary video path)
        self._mpv_proc: subprocess.Popen | None = None
        # cv2 fallback (threaded)
        self._video_frame_surf: pygame.Surface | None = None
        self._video_fps    = 30
        self._video_accum  = 0.0
        self._frame_queue: queue.Queue | None = None
        self._decode_thread: threading.Thread | None = None

    # ------------------------------------------------------------------

    def on_enter(self):
        self._elapsed      = 0.0
        self._transitioned = False
        ctx      = self.app.context
        scene_id = ctx.greeting_scene_id()
        self._scene = self.app.config.get_scene_by_id(scene_id) if scene_id else None

        logger.info(
            "IntroScreen.on_enter: path=%s | scene_id=%s | scene_found=%s | capture_count=%d",
            ctx.current_path.get("name") if ctx.current_path else None,
            scene_id, self._scene is not None, ctx.capture_count(),
        )

        if self._scene:
            self._duration = min(float(self._scene.get("duration", 5.0)), float(SCENE_GREETING_MAX))
            media = self._scene.get("media_type", "?")
            logger.info("IntroScreen: scene '%s', type=%s, duration=%.1fs",
                        self._scene.get("name"), media, self._duration)
            self._setup_media()
        else:
            self._duration = 3.0
            if scene_id:
                logger.warning("IntroScreen: scene_id '%s' not found in scenes.json – "
                               "playing 3s blank, then checking capture_count", scene_id)
                self.app.show_notification(
                    f"Szene '{scene_id}' nicht gefunden – bitte Pfad prüfen.",
                    level="warning"
                )
            else:
                logger.warning("IntroScreen: no greeting scene assigned to this path")

    def on_exit(self):
        self.app.audio.stop_music()
        # Terminate mpv if running
        if self._mpv_proc:
            self._mpv_proc.terminate()
            try:
                self._mpv_proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._mpv_proc.kill()
            self._mpv_proc = None
        # Stop cv2 worker (daemon thread exits when queue ref is dropped)
        self._frame_queue = None
        self._decode_thread = None
        self._video_frame_surf = None

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event):
        pass  # No user interaction during intro

    def update(self, dt: float):
        self._elapsed += dt
        self._advance_video(dt)

        if self._elapsed >= self._duration and not self._transitioned:
            self._transitioned = True
            ctx = self.app.context
            count = ctx.capture_count()
            logger.info("IntroScreen: %.1fs elapsed (duration=%.1fs), capture_count=%d → next screen",
                        self._elapsed, self._duration, count)
            if count > 0:
                self.transition_to("capture")
            else:
                logger.info("IntroScreen: capture_count=0 → returning to start screen")
                ctx.current_path = None
                self.transition_to("start")

    def draw(self, surface: pygame.Surface):
        if self._mpv_proc is not None:
            # mpv window is on top; just fill black so there's no artefact behind it
            surface.fill(COLOR_BG)
            return
        if self._video_frame_surf:
            surface.blit(self._video_frame_surf, (0, 0))
        elif self._bg_surface:
            surface.blit(self._bg_surface, (0, 0))
        else:
            surface.fill(COLOR_BG)
            draw_text_centered(surface, "…", self._fm(),
                               COLOR_TEXT, SCREEN_W // 2, SCREEN_H // 2)

    # ------------------------------------------------------------------

    def _setup_media(self):
        if not self._scene:
            return
        media_type = self._scene.get("media_type", "photo")
        if media_type == "video":
            self._load_video()
        else:
            self._load_image_bg()
            audio_path = self._scene.get("audio", "")
            if audio_path:
                p = self.app.config.resolve_asset(audio_path)
                if p.exists():
                    self.app.audio.play_music(p)

    def _load_image_bg(self):
        img_path = self._scene.get("image", "") if self._scene else ""
        if img_path:
            surf = self._load_image_scaled(img_path, (SCREEN_W, SCREEN_H))
            if surf:
                self._bg_surface = surf
                return
        self._bg_surface = None

    def _load_video(self):
        if not self._scene:
            self._load_image_bg()
            return
        video_path = self._scene.get("video", "")
        p = self.app.config.resolve_asset(video_path)
        if not p.exists():
            self._load_image_bg()
            return

        # Primary: mpv with hardware decoding
        try:
            args = [
                "mpv",
                "--fullscreen",
                "--hwdec=auto",      # use V4L2M2M / MMAL on Pi 4
                "--no-osc",
                "--really-quiet",
                "--no-terminal",
                "--loop-file=yes",   # loop short videos to fill the scene duration
                f"--end={self._duration:.1f}",
                str(p),
            ]
            self._mpv_proc = subprocess.Popen(args)
            logger.info("IntroScreen: mpv launched for '%s' (%.1fs)", p.name, self._duration)
            return
        except FileNotFoundError:
            logger.warning("mpv not found – install with: sudo apt install mpv")

        # Fallback: threaded cv2 decoder
        if _CV2:
            self._load_video_cv2(p)
        else:
            self._load_image_bg()

    def _load_video_cv2(self, p: Path):
        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            self._load_image_bg()
            return
        self._video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
        self._video_frame_surf = pygame.Surface((SCREEN_W, SCREEN_H))
        frame_q: queue.Queue = queue.Queue(maxsize=4)
        self._frame_queue = frame_q

        def _worker():
            while True:
                ret, frame = cap.read()
                if not ret:
                    # Loop back to start instead of stopping
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret:
                        cap.release()
                        return
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = cv2.resize(frame, (SCREEN_W, SCREEN_H), interpolation=cv2.INTER_LINEAR)
                try:
                    frame_q.put(frame, timeout=1.0)
                except queue.Full:
                    pass  # drop if consumer fell behind

        self._decode_thread = threading.Thread(target=_worker, daemon=True)
        self._decode_thread.start()
        logger.info("IntroScreen: cv2 threaded decoder started for '%s'", p.name)

    def _advance_video(self, dt: float):
        if self._mpv_proc is not None:
            return  # mpv handles its own playback
        if self._frame_queue is None or self._video_frame_surf is None:
            return
        self._video_accum += dt
        frame_time = 1.0 / self._video_fps
        while self._video_accum >= frame_time:
            self._video_accum -= frame_time
            try:
                frame = self._frame_queue.get_nowait()
                pygame.surfarray.blit_array(self._video_frame_surf,
                                            frame.transpose(1, 0, 2))
            except queue.Empty:
                break  # no decoded frame ready yet
