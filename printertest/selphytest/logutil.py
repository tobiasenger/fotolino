"""Logging setup: everything goes to stdout AND a timestamped file in printertest/logs/."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"


def setup_logging(command: str, verbose: bool = False) -> Path:
    """Configure root logging. Returns the path of the log file for this run."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    logfile = LOG_DIR / f"{ts}_{command}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(ch)

    logging.getLogger("selphytest").debug(
        "command=%s argv=%s logfile=%s", command, sys.argv, logfile
    )
    return logfile
