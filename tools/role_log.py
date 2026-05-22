"""Backward-compatibility shim — delegates to tools.hub.role_log."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.hub.role_log import *
