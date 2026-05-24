#!/usr/bin/env python3
"""
Tool Status — query which tools are installed and where.

Usage:
    python tool_status.py                   # Show all tools
    python tool_status.py --role pentest    # Show pentest tools only
    python tool_status.py --find tshark     # Find specific tool
    python tool_status.py --json            # Output as JSON (for AI parsing)
    python tool_status.py --missing         # Show only missing tools
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
MANIFEST_PATH = SCRIPT_DIR / "manifest.yaml"


def _decode_subprocess_output(raw):
    """Robust decode for subprocess byte output.

    Handles WSL.exe quirk: ``wsl.exe`` on Windows defaults to UTF-16 LE + BOM
    on stdout, which crashes ``text=True`` decoding under Chinese (gbk) locales
    with ``UnicodeDecodeError: 0xff``.
    """
    if not raw:
        return ""
    if raw[:2] == b"\xff\xfe":
        try:
            return raw.decode("utf-16-le", errors="replace").lstrip("\ufeff")
        except Exception:
            pass
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", errors="replace")


def load_manifest():
    try:
        import yaml
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"], check=False, timeout=60)
        import yaml

    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_tool(tool_def):
    """Return (available: bool, path: str|None)."""
    check_cmd = tool_def.get("check_cmd")

    # Try check_cmd
    if check_cmd:
        exe = check_cmd.split()[0]
        if exe == "python":
            # Python import check (bytes mode -> no decode crash)
            try:
                result = subprocess.run(
                    check_cmd, shell=True, capture_output=True, timeout=10
                )
                if result.returncode == 0:
                    return True, sys.executable
            except Exception:
                pass
        else:
            found = shutil.which(exe)
            if found:
                return True, found

    # Try known_paths
    for p in tool_def.get("known_paths") or []:
        expanded = os.path.expanduser(p)
        if os.path.exists(expanded):
            return True, expanded

    # Try WSL for tools with wsl install method
    installs = tool_def.get("install") or []
    has_wsl = any(isinstance(i, dict) and i.get("type") == "wsl" for i in installs)
    if has_wsl and check_cmd:
        try:
            if check_cmd.startswith("python"):
                wsl_cmd = check_cmd.replace("python", "python3", 1)
                result = subprocess.run(
                    ["wsl", "-e", "bash", "-c", wsl_cmd],
                    capture_output=True, timeout=5,
                )
            else:
                exe = check_cmd.split()[0]
                result = subprocess.run(
                    ["wsl", "--", "bash", "-lc", f"which {exe}"],
                    capture_output=True, timeout=5,
                )
            if result.returncode == 0:
                stdout_text = _decode_subprocess_output(result.stdout)
                path = stdout_text.strip() or check_cmd.split()[0]
                return True, f"WSL:{path}"
        except Exception:
            pass

    return False, None


def main():
    parser = argparse.ArgumentParser(description="AutoForensicAI tool status checker")
    parser.add_argument("--role", help="Filter by section/role name")
    parser.add_argument("--find", help="Find a specific tool by name")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--missing", action="store_true", help="Show only missing tools")
    parser.add_argument("--installed", action="store_true", help="Show only installed tools")
    args = parser.parse_args()

    manifest = load_manifest()
    skip_sections = {"meta", "docker_images"}
    results = []

    for section_name, section_data in manifest.items():
        if section_name in skip_sections:
            continue
        if not isinstance(section_data, dict):
            continue
        if args.role and args.role != section_name:
            continue

        for tool_name, tool_def in section_data.items():
            if not isinstance(tool_def, dict):
                continue
            if args.find and args.find.lower() not in tool_name.lower():
                continue

            available, path = check_tool(tool_def)

            if args.missing and available:
                continue
            if args.installed and not available:
                continue

            entry = {
                "name": tool_name,
                "section": section_name,
                "description": tool_def.get("description", ""),
                "available": available,
                "path": path,
                "roles": tool_def.get("roles", []),
                "note": tool_def.get("note", ""),
            }
            if not available and tool_def.get("install"):
                first = tool_def["install"][0]
                entry["install_hint"] = f"{first.get('type')}: {first.get('package') or first.get('id') or first.get('image') or first.get('url')}"
            results.append(entry)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # Pretty print
    current_section = None
    ok_count = 0
    miss_count = 0

    for r in results:
        if r["section"] != current_section:
            current_section = r["section"]
            print(f"\n=== {current_section.upper()} ===")

        if r["available"]:
            ok_count += 1
            loc = r["path"] or "?"
            print(f"  \033[32m[OK]\033[0m {r['name']:20s} {loc}")
        else:
            miss_count += 1
            hint = r.get("install_hint", "")
            print(f"  \033[33m[--]\033[0m {r['name']:20s} {hint}")

    print(f"\n--- {ok_count} installed, {miss_count} missing ---")
    if miss_count > 0:
        print("Run: .\\install.ps1 to install missing tools")


if __name__ == "__main__":
    main()
