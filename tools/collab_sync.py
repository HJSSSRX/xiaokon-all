#!/usr/bin/env python3
"""Backward-compatibility shim — delegates to tools.collab.sync_cli."""

from tools.collab.sync_cli import main

if __name__ == "__main__":
    main()
