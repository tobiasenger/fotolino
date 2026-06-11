"""selphytest — standalone diagnostic & test utility for the Canon SELPHY CP1500 on CUPS/Gutenprint.

Completely independent from the photo booth application.
"""

from __future__ import annotations

__version__ = "1.0.0"

# IPP job states (RFC 8011 section 5.3.7)
JOB_STATES = {
    3: "pending",
    4: "held",
    5: "processing",
    6: "stopped",
    7: "canceled",
    8: "aborted",
    9: "completed",
}

# IPP printer states
PRINTER_STATES = {
    3: "idle",
    4: "processing",
    5: "stopped",
}

# The backend that works with SELPHY dye-sub printers (Gutenprint >= 5.3)
GOOD_BACKEND_PREFIX = "gutenprint53+usb://"
# The backend known to cause "Waiting for printer to become available"
BAD_BACKEND_PREFIX = "usb://"


def cups_module():
    """Import pycups lazily with a helpful error message."""
    try:
        import cups
        return cups
    except ImportError:
        raise SystemExit(
            "ERROR: pycups is not installed.\n"
            "On Raspberry Pi OS install it via apt:  sudo apt install python3-cups"
        )


def connect():
    """Open a connection to the local CUPS server."""
    cups = cups_module()
    try:
        return cups.Connection()
    except RuntimeError as exc:
        raise SystemExit(
            f"ERROR: cannot connect to CUPS: {exc}\n"
            "Is the CUPS service running?  sudo systemctl status cups"
        )
