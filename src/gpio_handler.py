import logging

logger = logging.getLogger(__name__)

try:
    from gpiozero import Button, LED
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False
    logger.info("gpiozero not available – using keyboard fallback (SPACE / F1)")


class _MockLED:
    """Stub when GPIO is unavailable."""
    def on(self):  pass
    def off(self): pass
    @property
    def is_active(self): return False


class GPIOHandler:
    def __init__(self, config_manager, button_callback):
        """
        button_callback: callable(action: str) invoked from the GPIO thread.
        In the PyQt6 app this is a pyqtSignal.emit, which auto-queues the call
        onto the main (GUI) thread.
        """
        self._callback = button_callback
        pins = config_manager.gpio_pins()
        self._flash_enabled = config_manager.settings.get("flash_enabled", True)

        if _GPIO_AVAILABLE:
            try:
                self._start_btn  = Button(pins["pin_start_button"], pull_up=True, bounce_time=0.1)
                self._admin_btn  = Button(pins["pin_admin_button"],  pull_up=True, bounce_time=0.1)
                self._led_flash  = LED(pins["pin_led_flash"])
                self._led_ready  = LED(pins["pin_led_ready"])
                self._start_btn.when_pressed = lambda: self._fire("start_button")
                self._admin_btn.when_pressed = lambda: self._fire("admin_button")
                logger.info("GPIO initialised on pins %s", pins)
            except Exception as e:
                logger.warning("GPIO setup failed (%s) – falling back to keyboard", e)
                self._led_flash = _MockLED()
                self._led_ready = _MockLED()
        else:
            self._led_flash = _MockLED()
            self._led_ready = _MockLED()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, action: str):
        try:
            self._callback(action)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # LED control
    # ------------------------------------------------------------------

    def set_flash_led(self, on: bool):
        if self._flash_enabled:
            self._led_flash.on() if on else self._led_flash.off()

    def set_ready_led(self, on: bool):
        self._led_ready.on() if on else self._led_ready.off()

    # ------------------------------------------------------------------

    def cleanup(self):
        self.set_flash_led(False)
        self.set_ready_led(False)
