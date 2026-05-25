#!/usr/bin/env python3
"""Backward-compatibility shim — delegates to tools.kb.comp_search.

All logic now lives in tools.kb.comp_search.
This file preserves the fic_kb_search name for tests and prompts that
reference it directly (e.g. `import fic_kb_search; fic_kb_search.resolve_kb_root(...)`).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Re-export everything from comp_search for backward compat
from tools.kb.comp_search import *  # noqa: F401, F403

if __name__ == "__main__":
    from tools.kb.comp_search import main
    main()
