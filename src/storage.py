import logging
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from .constants import COLLAGE_LAYOUTS

logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self, config_manager):
        self._cfg = config_manager

    # ------------------------------------------------------------------

    def _usb_dir(self, subdir: str) -> Path:
        usb = self._cfg.usb_path()
        if not usb.exists():
            raise IOError(
                f"USB-Stick nicht gefunden unter '{usb}'. "
                "Bitte USB-Stick einstecken und sicherstellen, dass er unter "
                f"'{usb}' eingehängt ist. "
                "Mount prüfen: `lsblk` oder `df -h`"
            )
        path = usb / subdir
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise IOError(
                f"Ordner '{path}' konnte nicht erstellt werden: {e}. "
                "Bitte Schreibrechte und Dateisystem des USB-Sticks prüfen."
            ) from e
        return path

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    # ------------------------------------------------------------------
    # Photos
    # ------------------------------------------------------------------

    def save_photo(self, frame_rgb: np.ndarray, index: int) -> Path:
        """Save a raw RGB numpy frame as JPEG. Returns the saved path."""
        dest_dir  = self._usb_dir("Fotos")
        filename  = f"foto_{self._timestamp()}_{index:02d}.jpg"
        dest      = dest_dir / filename
        try:
            img = Image.fromarray(frame_rgb, "RGB")
            img.save(dest, "JPEG", quality=95)
            logger.info("Foto gespeichert: %s", dest)
        except OSError as e:
            raise IOError(
                f"Foto konnte nicht gespeichert werden ({dest}): {e}. "
                "Bitte USB-Stick auf freien Speicherplatz und Schreibrechte prüfen. "
                f"Freier Speicher: {self.free_space_mb():.1f} MB"
            ) from e
        return dest

    # ------------------------------------------------------------------
    # Collages
    # ------------------------------------------------------------------

    def save_collage(self, collage_image: Image.Image) -> Path:
        dest_dir = self._usb_dir("Collagen")
        filename = f"collage_{self._timestamp()}.jpg"
        dest     = dest_dir / filename
        try:
            collage_image.save(dest, "JPEG", quality=95)
            logger.info("Collage gespeichert: %s", dest)
        except OSError as e:
            raise IOError(
                f"Collage konnte nicht gespeichert werden ({dest}): {e}."
            ) from e
        return dest

    # ------------------------------------------------------------------
    # Gallery (files of the most recent session)
    # ------------------------------------------------------------------

    def last_session_photos(self) -> list[Path]:
        """Photos of the most recent session, in capture order.

        Photo filenames end in the zero-based capture index
        (foto_<ts>_00.jpg, _01, …), which restarts at 00 every session:
        walking newest-first, the session ends at the first file with
        index 00. Capped at the largest collage layout as a guard against
        foreign file names.
        """
        session: list[Path] = []
        for p in self._list_images("Fotos"):
            session.append(p)
            if p.stem.endswith("_00") or len(session) >= max(COLLAGE_LAYOUTS):
                break
        return session[::-1]

    def last_session_collage(self) -> list[Path]:
        """The most recently saved collage (one session = one collage)."""
        return self._list_images("Collagen")[:1]

    def _list_images(self, subdir: str) -> list[Path]:
        """All images in the USB folder, newest first; [] if the stick is missing."""
        base = self._cfg.usb_path(subdir)
        try:
            files = [p for p in base.iterdir()
                     if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        except OSError:
            logger.info("Galerie: Ordner '%s' nicht lesbar oder USB-Stick fehlt.", base)
            return []

        def mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0

        # Name as tie-breaker: equal mtimes keep …_02 after …_01.
        files.sort(key=lambda p: (mtime(p), p.name), reverse=True)
        return files

    # ------------------------------------------------------------------
    # USB health check
    # ------------------------------------------------------------------

    def usb_available(self) -> bool:
        usb = self._cfg.usb_path()
        return usb.exists() and usb.is_dir()

    def free_space_mb(self) -> float:
        usb = self._cfg.usb_path()
        try:
            usage = shutil.disk_usage(usb)
            return usage.free / (1024 * 1024)
        except Exception:
            return 0.0

    def prepare_usb(self) -> str:
        """Create the required storage folders on the USB drive.

        Returns a status message suitable for display in the UI.
        Raises IOError if the USB drive is not mounted or not writable.
        """
        usb = self._cfg.usb_path()
        if not usb.exists():
            raise IOError(
                f"USB-Stick nicht gefunden unter '{usb}'. "
                "Bitte USB-Stick einstecken."
            )
        created = []
        for folder in ("Fotos", "Collagen"):
            p = usb / folder
            if not p.exists():
                try:
                    p.mkdir(parents=True)
                    created.append(folder)
                    logger.info("USB-Ordner erstellt: %s", p)
                except OSError as e:
                    raise IOError(
                        f"Ordner '{folder}' konnte nicht erstellt werden: {e}"
                    ) from e
            else:
                logger.info("USB-Ordner bereits vorhanden: %s", p)

        free = self.free_space_mb()
        if created:
            return (
                f"USB-Stick vorbereitet. Erstellt: {', '.join(created)}. "
                f"Freier Speicher: {free:.0f} MB"
            )
        return (
            f"USB-Stick bereits eingerichtet (Fotos/ und Collagen/ vorhanden). "
            f"Freier Speicher: {free:.0f} MB"
        )
