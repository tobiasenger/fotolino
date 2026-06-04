"""
Fotobox – main entry point.

Usage:
    python src/main.py            # production (fullscreen)
    python src/main.py --dev      # dev mode: windowed + keyboard GPIO fallback + mock camera
"""
import argparse
import logging
import sys
from pathlib import Path

import pygame

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.constants   import SCREEN_W, SCREEN_H, BUTTON_EVENT, SCREEN_TRANSITION, COLOR_BG
from src.config_manager import ConfigManager
from src.state          import AppContext, AppState
from src.gpio_handler   import GPIOHandler
from src.audio          import AudioPlayer
from src.camera         import CameraController
from src.storage        import StorageManager
from src.collage        import CollageCreator
from src.printer        import Printer

from src.ui.screen_start   import StartScreen
from src.ui.screen_intro   import IntroScreen
from src.ui.screen_capture import CaptureScreen
from src.ui.screen_collage import CollageScreen
from src.ui.screen_print   import PrintScreen
from src.ui.admin.admin_main import AdminMain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("fotobox.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fotobox.main")


class App:
    def __init__(self, dev_mode: bool = False):
        self.dev_mode = dev_mode

        # Core
        self.config         = ConfigManager()
        self.context        = AppContext()
        self.gpio           = GPIOHandler(self.config)
        self.audio          = AudioPlayer()
        self.camera         = CameraController(
            self.config.settings.get("screen_width",  SCREEN_W),
            self.config.settings.get("screen_height", SCREEN_H),
        )
        self.storage        = StorageManager(self.config)
        self.collage_creator = CollageCreator(self.config)
        self.printer        = Printer(self.config)

        # pygame
        pygame.init()
        pygame.font.init()

        use_fullscreen = (not dev_mode) and self.config.settings.get("fullscreen", True)
        flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF if use_fullscreen \
            else pygame.RESIZABLE
        w = self.config.settings.get("screen_width",  SCREEN_W)
        h = self.config.settings.get("screen_height", SCREEN_H)
        if dev_mode:
            w, h = min(w, 1280), min(h, 720)

        self.surface = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption("Fotobox")
        if use_fullscreen:
            pygame.mouse.set_visible(False)

        # Notification overlay
        self._notify_font = pygame.font.SysFont("dejavusans,freesans,sans-serif", 26)
        self._notifications: list = []  # [(message, expire_seconds, level)]

        # Screens
        self.screens: dict = {
            "start":   StartScreen(self),
            "intro":   IntroScreen(self),
            "capture": CaptureScreen(self),
            "collage": CollageScreen(self),
            "print":   PrintScreen(self),
            "admin":   AdminMain(self),
        }
        self._current_screen = self.screens["start"]
        self._current_screen.on_enter()

        logger.info("Fotobox started (dev=%s, display=%dx%d)", dev_mode, w, h)

    # ------------------------------------------------------------------

    def run(self):
        clock = pygame.time.Clock()
        running = True

        while running:
            dt = clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        continue
                    self.gpio.handle_keyboard_event(event)

                if event.type == BUTTON_EVENT:
                    self._handle_button(event)
                    continue  # button events are handled centrally; don't also pass to screen

                if event.type == SCREEN_TRANSITION:
                    target = getattr(event, "target", None)
                    if target:
                        self._switch_screen(target)
                    continue

                self._current_screen.handle_event(event)

            self._current_screen.update(dt)

            self.surface.fill(COLOR_BG)
            self._current_screen.draw(self.surface)
            self._draw_notifications()
            pygame.display.flip()

        self._cleanup()

    # ------------------------------------------------------------------

    def _handle_button(self, event: pygame.event.Event):
        action = getattr(event, "action", None)

        if action == "start_button":
            if self.context.state == AppState.READY:
                path = self.config.select_random_path()
                if path:
                    if not self.storage.usb_available():
                        self.show_notification(
                            "USB-Stick nicht gefunden – Fotos können nicht gespeichert werden",
                            level="warning"
                        )
                    self.context.start_path(path)
                    self._switch_screen("intro")
                else:
                    self.show_notification(
                        "Keine Pfade konfiguriert – Admin-Taste drücken um Pfade anzulegen",
                        duration=6.0, level="warning"
                    )

        elif action == "admin_button":
            if self.context.state == AppState.ADMIN:
                self.context.exit_admin()
                self._switch_screen("start")
            else:
                # Allow entering admin from any state except mid-capture/collage/print
                if self.context.state in (AppState.READY, AppState.INTRO):
                    self.context.enter_admin()
                    self._switch_screen("admin")

    def _switch_screen(self, name: str):
        if name not in self.screens:
            logger.warning("Unknown screen: %s", name)
            return
        self._current_screen.on_exit()
        self._current_screen = self.screens[name]
        # Keep context state in sync
        state_map = {
            "start":   AppState.READY,
            "intro":   AppState.INTRO,
            "capture": AppState.CAPTURE,
            "collage": AppState.COLLAGE,
            "print":   AppState.PRINT,
            "admin":   AppState.ADMIN,
        }
        if name in state_map and self.context.state != AppState.ADMIN:
            self.context.state = state_map[name]
        self._current_screen.on_enter()
        logger.info("Screen → %s", name)

    def show_notification(self, message: str, duration: float = 7.0, level: str = "info"):
        """Show an on-screen notification overlay. level: 'info' | 'warning' | 'error'"""
        expire = pygame.time.get_ticks() / 1000.0 + duration
        self._notifications.append((message, expire, level))
        log_level = {"error": logging.ERROR, "warning": logging.WARNING}.get(level, logging.INFO)
        logger.log(log_level, "[Notification] %s", message)

    def _draw_notifications(self):
        now = pygame.time.get_ticks() / 1000.0
        self._notifications = [n for n in self._notifications if n[1] > now]
        if not self._notifications:
            return
        colors = {
            "error":   (220,  60,  60),
            "warning": (255, 190,   0),
            "info":    ( 80, 210, 100),
        }
        y = 20
        for msg, _, level in self._notifications[-5:]:
            color = colors.get(level, (220, 220, 220))
            text_surf = self._notify_font.render(msg, True, (255, 255, 255))
            tw, th = text_surf.get_size()
            bg = pygame.Surface((tw + 48, th + 18), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 210))
            self.surface.blit(bg, (20, y))
            pygame.draw.rect(self.surface, color, (20, y, 5, th + 18))  # coloured left stripe
            self.surface.blit(text_surf, (34, y + 9))
            y += th + 26

    def _cleanup(self):
        logger.info("Shutting down…")
        self.gpio.cleanup()
        self.camera.cleanup()
        self.audio.stop_all()
        pygame.quit()


# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fotobox")
    parser.add_argument("--dev", action="store_true",
                        help="Development mode: windowed, keyboard buttons, mock camera")
    args = parser.parse_args()

    app = App(dev_mode=args.dev)
    app.run()


if __name__ == "__main__":
    main()
