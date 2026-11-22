#!/usr/bin/env python3
"""Entry point: python scripts/gaming_phase1_cli.py <command> ..."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.gaming_phase1.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
