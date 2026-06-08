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
    """Wraps picamera2 with a graceful mock fallback for development."""

    def __init__(self, width: int = 1920, height: int = 1080):
        self._w = width
        self._h = height
        self._cam = None
        self._streaming = False

        if _PICAM_AVAILABLE:
            try:
                self._cam = Picamera2()
                cfg = self._cam.create_preview_configuration(
                    main={"size": (width, height), "format": "RGB888"},
                    controls={"FrameDurationLimits": (33333, 33333)},
                )
                self._cam.configure(cfg)
                logger.info("Camera initialised at %dx%d", width, height)
            except Exception as e:
                logger.warning("Camera init failed (%s) – using mock", e)
                self._cam = None

    # ------------------------------------------------------------------

    def start(self):
        if self._cam and not self._streaming:
            self._cam.start()
            self._streaming = True

    def stop(self):
        if self._cam and self._streaming:
            self._cam.stop()
            self._streaming = False

    def get_frame_rgb(self) -> np.ndarray:
        """Return current frame as (H, W, 3) RGB uint8 array."""
        if self._cam and self._streaming:
            try:
                return self._cam.capture_array("main")
            except Exception as e:
                logger.warning("Frame capture error: %s", e)
        return self._mock_frame()

    def capture_photo(self) -> np.ndarray:
        """Capture a high-quality still as (H, W, 3) RGB uint8."""
        if self._cam and self._streaming:
            try:
                return self._cam.capture_array("main")
            except Exception as e:
                logger.warning("Photo capture error: %s", e)
        return self._mock_frame()

    def get_qpixmap(self, mirror: bool = True):
        """Return the current frame as a QPixmap."""
        from PyQt6.QtGui import QImage, QPixmap
        frame = self.get_frame_rgb()
        if mirror:
            frame = frame[:, ::-1, :]              # horizontal flip
        # Ensure C-contiguous memory for QImage.
        frame = np.ascontiguousarray(frame)
        h, w, c = frame.shape
        qimg = QImage(frame.data, w, h, c * w, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())      # .copy() to own the data

    def is_connected(self) -> bool:
        return self._cam is not None

    @property
    def resolution(self) -> tuple:
        return (self._w, self._h)

    # ------------------------------------------------------------------

    def _mock_frame(self) -> np.ndarray:
        """A grey gradient test pattern."""
        frame = np.zeros((self._h, self._w, 3), dtype=np.uint8)
        ramp = np.linspace(40, 100, self._w, dtype=np.uint8)
        frame[:, :, 0] = ramp
        frame[:, :, 1] = 60
        frame[:, :, 2] = ramp[::-1]
        # Draw a centred white rectangle as a viewfinder hint
        cx, cy = self._w // 2, self._h // 2
        frame[cy-200:cy+200, cx-300:cx+300] = 200
        return frame

    def cleanup(self):
        self.stop()
