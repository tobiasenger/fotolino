import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    _PICAM_AVAILABLE = True
except ImportError:
    _PICAM_AVAILABLE = False
    logger.info("picamera2 not available – using mock camera")


class CameraController:
    """Wraps picamera2 with a graceful mock fallback for development.

    Two configurations are prepared at init time:
      _preview_config – used during live preview (RGB888, screen resolution, ~30fps)
      _still_config   – switched to briefly at shutter press (full sensor resolution)

    During capture, switch_mode_and_capture_array() handles the config swap and
    automatically returns to the preview configuration afterwards.
    """

    def __init__(self, width: int = 1920, height: int = 1080):
        self._w = width
        self._h = height
        self._cam: "Picamera2 | None" = None
        self._streaming = False

        if _PICAM_AVAILABLE:
            try:
                self._cam = Picamera2()

                # Preview: screen resolution, 30 fps, hardware-decoded by ISP
                self._preview_config = self._cam.create_preview_configuration(
                    main={"size": (width, height), "format": "RGB888"},
                )
                # Still: full sensor resolution, auto-exposure settled before capture
                self._still_config = self._cam.create_still_configuration(
                    main={"size": self._cam.sensor_resolution},
                )
                self._cam.configure(self._preview_config)
                logger.info(
                    "Camera configured: preview %dx%d, still %s",
                    width, height, self._cam.sensor_resolution,
                )
            except Exception as e:
                logger.warning("Camera init failed (%s) – using mock", e)
                self._cam = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._cam and not self._streaming:
            self._cam.start()
            self._streaming = True
            logger.debug("Camera started")

    def stop(self):
        if self._cam and self._streaming:
            self._cam.stop()
            self._streaming = False
            logger.debug("Camera stopped")

    def cleanup(self):
        self.stop()

    # ------------------------------------------------------------------
    # Frame access
    # ------------------------------------------------------------------

    def get_frame_rgb(self) -> np.ndarray:
        """Return current preview frame as (H, W, 3) RGB uint8 array."""
        if self._cam and self._streaming:
            try:
                return self._cam.capture_array("main")
            except Exception as e:
                logger.warning("Frame capture error: %s", e)
        return self._mock_frame()

    def capture_photo(self) -> np.ndarray:
        """Capture a high-quality still using the full sensor resolution.

        The camera briefly switches to the still configuration, captures one
        frame, then restores the preview configuration automatically.
        """
        if self._cam and self._streaming:
            try:
                arr = self._cam.switch_mode_and_capture_array(
                    self._still_config, "main"
                )
                logger.info(
                    "Still captured at %dx%d", arr.shape[1], arr.shape[0]
                )
                return arr
            except Exception as e:
                logger.warning("Still capture failed (%s) – using preview frame", e)
                try:
                    return self._cam.capture_array("main")
                except Exception:
                    pass
        return self._mock_frame()

    def get_qpixmap(self, mirror: bool = True):
        """Return the current preview frame as a QPixmap (for polling fallback)."""
        from PyQt6.QtGui import QImage, QPixmap
        frame = self.get_frame_rgb()
        if mirror:
            frame = frame[:, ::-1, :]
        frame = np.ascontiguousarray(frame)
        h, w, c = frame.shape
        qimg = QImage(frame.data, w, h, c * w, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        return self._cam is not None

    @property
    def picam2(self):
        """Raw Picamera2 instance, needed by QGlPicamera2."""
        return self._cam

    @property
    def resolution(self) -> tuple:
        return (self._w, self._h)

    # ------------------------------------------------------------------

    def _mock_frame(self) -> np.ndarray:
        frame = np.zeros((self._h, self._w, 3), dtype=np.uint8)
        ramp = np.linspace(40, 100, self._w, dtype=np.uint8)
        frame[:, :, 0] = ramp
        frame[:, :, 1] = 60
        frame[:, :, 2] = ramp[::-1]
        cx, cy = self._w // 2, self._h // 2
        frame[cy - 200:cy + 200, cx - 300:cx + 300] = 200
        return frame
