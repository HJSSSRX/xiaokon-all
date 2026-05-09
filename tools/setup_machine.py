#!/usr/bin/env python3
"""
setup_machine.py — Multi-machine collaboration setup (one-shot).

Run once after `git clone`. Sets up:
  1. MACHINE_ID  → ~/.config/autoforensicai/machine.txt
  2. git config user.name = "cascade@<MACHINE_ID>"
  3. .git/hooks/commit-msg  → enforces [machine: ID] tag
  4. .git/hooks/pre-commit  → blocks INDEX hand-edits, runtime files

Usage:
  python tools/setup_machine.py                       # interactive
  python tools/setup_machine.py --id A_main           # explicit
  python tools/setup_machine.py --rename A_main NEW   # change ID
  python tools/setup_machine.py --status              # show current

See: docs/MULTI_MACHINE_CONTRIBUTION.md
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Windows GBK console fix — must run before any print() with non-ASCII content
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ───── Paths ─────

def config_dir() -> Path:
    """Per-OS user config dir."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "autoforensicai"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "autoforensicai"


MACHINE_FILE = config_dir() / "machine.txt"
REPO_ROOT = Path(__file__).resolve().parent.parent


# ───── MACHINE_ID I/O ─────

def read_machine_id() -> str | None:
    if MACHINE_FILE.exists():
        v = MACHINE_FILE.read_text(encoding="utf-8").strip()
        return v or None
    return None


def write_machine_id(mid: str) -> None:
    MACHINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MACHINE_FILE.write_text(mid + "\n", encoding="utf-8")


def default_id() -> str:
    host = platform.node().split(".")[0].lower().replace(" ", "_") or "host"
    return f"{host}_main"


# ───── Git config ─────

def git_set_user(mid: str) -> None:
    """Set per-repo git user.name to identify this machine in commits."""
    name = f"cascade@{mid}"
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "config", "user.name", name],
        check=True,
    )
    print(f"  ✓ git user.name = {name}")


# ───── Hooks ─────

COMMIT_MSG_HOOK = r"""#!/bin/sh
# Auto-installed by tools/setup_machine.py
# Enforces [machine: ID] tag in commit messages.
# Reads MACHINE_ID from ~/.config/autoforensicai/machine.txt (or %APPDATA% on Windows).

MSG_FILE="$1"

# Locate machine.txt (Windows or *nix)
if [ -n "$APPDATA" ]; then
    MACHINE_FILE="$APPDATA/autoforensicai/machine.txt"
else
    MACHINE_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/autoforensicai/machine.txt"
fi

if [ ! -f "$MACHINE_FILE" ]; then
    echo "[commit-msg] machine.txt not found at $MACHINE_FILE" >&2
    echo "             Run: python tools/setup_machine.py" >&2
    exit 1
fi

MACHINE_ID=$(cat "$MACHINE_FILE" | tr -d '\r\n')

# Check if message already has [machine: ...]
if grep -q "\[machine:" "$MSG_FILE"; then
    exit 0
fi

# Auto-append [machine: ID] to last non-empty line
python3 -c "
import sys
p = sys.argv[1]
mid = sys.argv[2]
with open(p, 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()
# Find last non-comment, non-empty line
for i in range(len(lines) - 1, -1, -1):
    if lines[i].strip() and not lines[i].lstrip().startswith('#'):
        lines[i] = lines[i] + ' [machine: ' + mid + ']'
        break
else:
    lines.append('[machine: ' + mid + ']')
with open(p, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
" "$MSG_FILE" "$MACHINE_ID"
"""

def get_hooks_dir() -> Path | None:
    """Resolve effective hooks dir, honoring core.hooksPath if set.

    Returns None if no usable hooks dir exists.
    """
    # 1. Check core.hooksPath config
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "config", "--get", "core.hooksPath"],
        capture_output=True, text=True, check=False,
    )
    raw = r.stdout.strip() if r.returncode == 0 else ""
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = REPO_ROOT / raw
        # Create if missing (so we can install into it)
        path.mkdir(parents=True, exist_ok=True)
        return path
    # 2. Default: .git/hooks (only valid if .git is a dir, not a worktree pointer)
    default = REPO_ROOT / ".git" / "hooks"
    if default.exists():
        return default
    return None


SETUP_MARKER = "Auto-installed by tools/setup_machine.py"


def render_combined_pre_commit(existing_content: str | None) -> str:
    """Build a pre-commit hook that runs our checks first, then any pre-existing hook body.

    If existing_content is None or already a setup_machine combined hook, we just emit
    a fresh combined version with no existing body.
    """
    body = ""
    if existing_content and SETUP_MARKER not in existing_content:
        # Strip leading shebang if present
        lines = existing_content.splitlines()
        if lines and lines[0].startswith("#!"):
            lines = lines[1:]
        body = "\n".join(lines).rstrip()

    our_checks = '''STAGED=$(git diff --cached --name-only)

# Rule 1: runtime state files
BAD=$(echo "$STAGED" | grep -E '(\\.db$|\\.db-journal$|/needs.*\\.json$|/role_status.*\\.json$|^progress\\.txt$|\\.draft\\.md$|^machine\\.txt$)' || true)
if [ -n "$BAD" ]; then
    echo "[pre-commit] BLOCKED: runtime state files in commit:" >&2
    echo "$BAD" | sed 's/^/  /' >&2
    echo "  Fix: git reset HEAD <file> ; add to .gitignore" >&2
    exit 1
fi

# Rule 2: INDEX hand-edit warning (not blocking)
INDEX_EDIT=$(echo "$STAGED" | grep -E 'INDEX\\.(yaml|md)$' || true)
if [ -n "$INDEX_EDIT" ]; then
    echo "[pre-commit] WARN: INDEX file edited manually:" >&2
    echo "$INDEX_EDIT" | sed 's/^/  /' >&2
    echo "  Tip: run 'python tools/build_kb_index.py' to auto-rebuild instead." >&2
fi'''

    if body:
        return f"""#!/bin/sh
# {SETUP_MARKER} — combined pre-commit hook
# Runs autoforensicai runtime/INDEX checks first, then pre-existing hook body below.

# === autoforensicai checks ===
{our_checks}

# === pre-existing pre-commit body (preserved verbatim) ===
{body}
# === END pre-existing body ===

exit 0
"""
    return f"""#!/bin/sh
# {SETUP_MARKER}
{our_checks}

exit 0
"""


def install_hooks() -> None:
    hooks_dir = get_hooks_dir()
    if hooks_dir is None:
        print(f"  ⚠ cannot find usable hooks dir (no core.hooksPath, no .git/hooks/)")
        return
    print(f"  hooks dir: {hooks_dir}")

    # 1. commit-msg (no merge needed; we own this hook)
    cm_path = hooks_dir / "commit-msg"
    if cm_path.exists() and SETUP_MARKER not in cm_path.read_text(encoding="utf-8", errors="ignore"):
        backup = cm_path.with_suffix(".bak")
        shutil.copy(cm_path, backup)
        print(f"  ⚠ existing commit-msg backed up to {backup.name}")
    cm_path.write_text(COMMIT_MSG_HOOK, encoding="utf-8", newline="\n")
    try:
        cm_path.chmod(0o755)
    except Exception:
        pass
    print(f"  ✓ installed commit-msg")

    # 2. pre-commit (merge with any pre-existing user hook)
    pc_path = hooks_dir / "pre-commit"
    existing = pc_path.read_text(encoding="utf-8", errors="ignore") if pc_path.exists() else None
    if existing and SETUP_MARKER not in existing:
        backup = pc_path.with_suffix(".bak")
        shutil.copy(pc_path, backup)
        print(f"  ⚠ existing pre-commit (user hook) backed up to {backup.name} and merged into combined hook")
    pc_path.write_text(render_combined_pre_commit(existing), encoding="utf-8", newline="\n")
    try:
        pc_path.chmod(0o755)
    except Exception:
        pass
    if existing and SETUP_MARKER not in existing:
        print(f"  ✓ installed pre-commit (combined: our checks + your prior hook)")
    else:
        print(f"  ✓ installed pre-commit")


# ───── .gitignore ─────

GITIGNORE_BLOCK = """
# ─── autoforensicai runtime state (auto-added by setup_machine.py) ───
data/collab_hub/*.db
data/collab_hub/*.db-journal
data/collab_hub/needs_*.json
data/collab_hub/role_status_*.json
progress.txt
worklog/personal_*.md
*.draft.md
.cache/
__pycache__/
*.pyc
machine.txt
.machine_id
tests/output/
htmlcov/
# ─── /autoforensicai runtime state ───
"""


def update_gitignore() -> None:
    gi = REPO_ROOT / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if "autoforensicai runtime state" in existing:
        print("  ✓ .gitignore already has runtime block")
        return
    with open(gi, "a", encoding="utf-8", newline="\n") as f:
        f.write(GITIGNORE_BLOCK)
    print(f"  ✓ appended runtime block to .gitignore")


# ───── Commands ─────

def cmd_setup(args) -> int:
    print(f"== ForHacker multi-machine setup ==")
    print(f"  repo:        {REPO_ROOT}")
    print(f"  config dir:  {config_dir()}")
    print()

    current = read_machine_id()
    if args.id:
        mid = args.id.strip()
    elif current:
        print(f"  Existing MACHINE_ID: {current}")
        ans = input(f"  Keep it? [Y/n] ").strip().lower()
        if ans in ("", "y", "yes"):
            mid = current
        else:
            mid = input(f"  New MACHINE_ID (default: {default_id()}): ").strip() or default_id()
    else:
        suggested = default_id()
        ans = input(f"  MACHINE_ID (default: {suggested}): ").strip()
        mid = ans or suggested

    # Validate
    if not mid.replace("_", "").replace("-", "").isalnum():
        print(f"  ✗ MACHINE_ID must be alphanumeric (with _ or -)", file=sys.stderr)
        return 1

    write_machine_id(mid)
    print(f"  ✓ MACHINE_ID = {mid} → {MACHINE_FILE}")
    print()

    git_set_user(mid)
    print()
    install_hooks()
    print()
    update_gitignore()
    print()
    print(f"== setup complete ==")
    print(f"  Test: git commit -m 'test' will auto-append [machine: {mid}]")
    return 0


def cmd_status(args) -> int:
    mid = read_machine_id()
    print(f"MACHINE_ID:    {mid or '(not set)'}")
    print(f"config file:   {MACHINE_FILE}")
    print(f"repo:          {REPO_ROOT}")
    if mid:
        try:
            r = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "config", "--get", "user.name"],
                capture_output=True, text=True, check=False,
            )
            print(f"git user.name: {r.stdout.strip()}")
        except Exception:
            pass
    hooks_dir = get_hooks_dir()
    if hooks_dir is None:
        print(f"hooks dir:     (no hooks dir found)")
        return 0
    print(f"hooks dir:     {hooks_dir}")
    for h in ["commit-msg", "pre-commit"]:
        p = hooks_dir / h
        if p.exists() and SETUP_MARKER in p.read_text(encoding="utf-8", errors="ignore"):
            print(f"hook {h}:    installed")
        elif p.exists():
            print(f"hook {h}:    EXISTS (not setup_machine; will be merged on next setup)")
        else:
            print(f"hook {h}:    NOT installed")
    return 0


def cmd_rename(args) -> int:
    old, new = args.old, args.new
    cur = read_machine_id()
    if cur != old:
        print(f"  Current ID is {cur!r}, not {old!r}", file=sys.stderr)
        return 1
    write_machine_id(new)
    git_set_user(new)
    print(f"  Renamed: {old} → {new}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", help="explicit MACHINE_ID (skip prompt)")
    ap.add_argument("--status", action="store_true", help="show current status")
    ap.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"), help="rename existing ID")
    args = ap.parse_args()

    if args.status:
        return cmd_status(args)
    if args.rename:
        args.old, args.new = args.rename
        return cmd_rename(args)
    return cmd_setup(args)


if __name__ == "__main__":
    sys.exit(main())
