#!/usr/bin/env python3
"""Backward-compatibility shim — delegates to tools.kb.sync_kb."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.kb.sync_kb import main

if __name__ == "__main__":
    main()
