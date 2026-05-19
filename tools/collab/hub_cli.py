#!/usr/bin/env python3
"""CLI entry point for collaboration hub."""

import argparse

from .hub_server import cmd_serve


def main():
    parser = argparse.ArgumentParser(description="AutoForensicAI Collaboration Hub v3")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("serve", help="Start the Hub")
    p.add_argument("case_dir", help="Path to case directory")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--bind", default="0.0.0.0")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
