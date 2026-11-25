#!/usr/bin/env python3
"""
parley_diario_fd.py — Wrapper legacy que delega en la arquitectura modular src.parley.cli
"""

import sys
from pathlib import Path

# Añadir src al path para permitir ejecución directa
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from parley.cli import main

if __name__ == "__main__":
    # Forzar provider fd si se ejecuta este script
    if "--provider" not in sys.argv:
        sys.argv.extend(["--provider", "fd"])
    main()
