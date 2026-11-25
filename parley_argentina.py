#!/usr/bin/env python3
"""
parley_argentina.py — Wrapper legacy que delega en la arquitectura modular src.parley.cli (Bzzoiro)
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from parley.cli import main

if __name__ == "__main__":
    if "--provider" not in sys.argv:
        sys.argv.extend(["--provider", "bzzoiro"])
    main()
