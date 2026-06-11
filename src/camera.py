import logging
import numpy as np

logger = logging.getLogger(__name__)

# picamera2 is imported lazily inside __init__ so it only loads AFTER
# QApplication is constructed.  picamera2's package __init__ transitively
# imports picamera2.previews.gl (OpenGL preview), which tries to create a
# QOpenGLWidget before QApplication exists and causes a Qt abort.


class CameraController:
    """Wraps picamera2 with a graceful mock fallback for development.

    Preview configuration uses the screen resolution; still capture switches
    temporarily to the full sensor resolution for maximum photo quality.
    """

    def __init__(self, width: int = 1920, height: int = 1080):
        self._w = width
        self._h = height
        self._cam = None
        self._streaming = False
        self._preview_config = None
        self._still_config = None

        try:
            from picamera2 import Picamera2  # deferred – see module docstring
            cam = Picamera2()

            preview_cfg = cam.create_preview_configuration(
                main={"size": (width, height), "format": "RGB888"},
            )
            try:
                still_cfg = cam.create_still_configuration(
                    main={"size": cam.sensor_resolution},
                )
            except Exception as e:
                still_cfg = preview_cfg   # fall back to preview quality
                logger.warning(
                    "Still-Konfiguration fehlgeschlagen (%s) – Fotos werden in "
                    "Vorschau-Auflösung (%dx%d) aufgenommen.", e, width, height)

            cam.configure(preview_cfg)
            self._cam = cam
            self._preview_config = preview_cfg
            self._still_config = still_cfg
            logger.info(
                "Kamera bereit: Vorschau %dx%d, Foto-Auflösung %s",
                width, height,
                getattr(cam, "sensor_resolution", "unbekannt"),
            )
        except ImportError:
            logger.info("picamera2 nicht installiert – Mock-Kamera (Testbild) aktiv")
        except Exception as e:
            logger.warning(
                "Kamera-Initialisierung fehlgeschlagen (%s) – Mock-Kamera "
                "(Testbild) aktiv. Kabel prüfen und mit `rpicam-hello` testen.", e)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._cam and not self._streaming:
            self._cam.start()
            self._streaming = True
            logger.debug("Kamera-Vorschau gestartet")

    def stop(self):
        if self._cam and self._streaming:
            self._cam.stop()
            self._streaming = False
            logger.debug("Kamera-Vorschau gestoppt")

    def cleanup(self):
        self.stop()

    # ------------------------------------------------------------------
    # Frame access
    # ------------------------------------------------------------------

    def get_frame_rgb(self) -> np.ndarray:
        """Current preview frame as (H, W, 3) RGB uint8 array."""
        if self._cam and self._streaming:
            try:
                return self._cam.capture_array("main")
            except Exception as e:
                logger.warning(
                    "Vorschaubild konnte nicht gelesen werden (%s) – "
                    "Testbild wird angezeigt.", e)
        return self._mock_frame()

    def capture_photo(self) -> np.ndarray:
        """Capture a still at full sensor resolution.

        Uses switch_mode_and_capture_array so the camera briefly switches to
        the still configuration and then automatically returns to preview mode.
        Falls back to a preview frame if this fails.
        """
        if self._cam and self._streaming:
            try:
                arr = self._cam.switch_mode_and_capture_array(
                    self._still_config, "main"
                )
                logger.info("Foto aufgenommen (%dx%d)", arr.shape[1], arr.shape[0])
                return arr
            except Exception as e:
                logger.warning(
                    "Foto-Aufnahme in voller Auflösung fehlgeschlagen (%s) – "
                    "Vorschaubild wird verwendet.", e)
                try:
                    return self._cam.capture_array("main")
                except Exception:
                    pass
        return self._mock_frame()

    def get_qpixmap(self, mirror: bool = True):
        """Current frame as QPixmap (polling fallback when QGlPicamera2 unavailable)."""
        from PyQt6.QtGui import QImage, QPixmap
        frame = self.get_frame_rgb()
        if mirror:
            frame = frame[:, ::-1, :]
        frame = np.ascontiguousarray(frame)
        h, w, c = frame.shape
        qimg = QImage(frame.data, w, h, c * w, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    # ------------------------------------------------------------------
    # Status / properties
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
