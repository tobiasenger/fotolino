#!/usr/bin/env python3
"""Launcher for the standalone SELPHY CP1500 diagnostic & test utility.

Usage:  python3 selphy_test.py <command> [options]
Run     python3 selphy_test.py --help   for all commands.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from selphytest.cli import main

if __name__ == "__main__":
    sys.exit(main())
