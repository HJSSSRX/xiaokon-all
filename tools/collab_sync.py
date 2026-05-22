#!/usr/bin/env python3
"""Backward-compatibility shim — delegates to tools.collab.sync_cli."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.collab.sync_cli import main

if __name__ == "__main__":
    main()
