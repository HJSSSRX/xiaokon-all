"""Hub server bootstrap: IP discovery, shared file init, serve loop."""

import http.server
import socket
import sys
from pathlib import Path

from ..core import now_str, save_yaml
from .hub_constants import _HUB_STARTED_AT  # noqa: F401 - re-exported for mutation
from .hub_handler import Handler


def get_local_ips():
    """Discover all local IP addresses."""
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ips)


def init_shared_files(case_dir):
    """Ensure all required shared YAML files exist."""
    sd = Path(case_dir) / "shared"
    sd.mkdir(parents=True, exist_ok=True)
    defaults = {
        "findings.yaml": [],
        "progress.yaml": {},
        "answers.yaml": {},
        "questions.yaml": [],
        "timeline.yaml": [],
        "session_log.yaml": [],
        "blockers.yaml": [],
        "strategy.yaml": {},
    }
    for fname, default in defaults.items():
        fpath = sd / fname
        if not fpath.exists():
            save_yaml(fpath, default)


def cmd_serve(args):
    """Start the collaboration hub server."""
    from . import hub_constants
    case_dir = Path(args.case_dir).resolve()
    if not case_dir.exists():
        print(f"[!] Case directory not found: {case_dir}")
        sys.exit(1)

    init_shared_files(case_dir)
    Handler.case_dir = case_dir
    hub_constants._HUB_STARTED_AT = now_str()

    server = http.server.ThreadingHTTPServer((args.bind, args.port), Handler)

    print()
    print("=" * 60)
    print(f"  Collaboration Hub v3  -  port {args.port}")
    print("=" * 60)
    print(f"  Case dir:  {case_dir}")
    print(f"  Bind:      {args.bind}:{args.port}")
    print()
    print("  Remote machines connect via:")
    for ip in get_local_ips():
        if not ip.startswith("127."):
            print(f"    curl http://{ip}:{args.port}/ping")
    print()
    print("  Press Ctrl+C to stop.")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Hub stopped.")


def main():
    import argparse
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
