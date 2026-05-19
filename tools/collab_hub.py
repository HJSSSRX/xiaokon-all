#!/usr/bin/env python3
"""Backward-compatibility shim — delegates to tools.collab.hub_cli."""

from tools.collab.hub_cli import main

if __name__ == "__main__":
    main()
