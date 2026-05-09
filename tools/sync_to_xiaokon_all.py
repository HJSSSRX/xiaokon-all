#!/usr/bin/env python3
"""
sync_to_xiaokon_all.py — Build xiaokon-all monorepo from framework + data.

The xiaokon-all repo is a monorepo snapshot for quick deployment, combining:
  * framework (xiaokon_autoforensicai): tools/ tests/ docs/ etc.
  * data (autoforensicai_data):         knowledge/ cases/

Strategy:
  1. Detect both local clones (framework cwd, data via env or arg).
  2. Pull both to latest origin/main.
  3. Build a temp working tree containing union of files.
  4. Merge into a separate xiaokon-all clone, commit, push.

Why not just `git push`? Framework and data have non-overlapping content;
direct push would delete the other side's files. Monorepo requires explicit
union construction.

Usage:
  python tools/sync_to_xiaokon_all.py
  python tools/sync_to_xiaokon_all.py --all-repo e:/xiaokon-all
  python tools/sync_to_xiaokon_all.py --dry-run

Setup (one-time, on each machine):
  git clone https://github.com/HJSSSRX/autoforensicai_data.git e:/autoforensicai_data
  git clone https://github.com/HJSSSRX/xiaokon-all.git           e:/xiaokon-all

See: docs/MULTI_MACHINE_CONTRIBUTION.md
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent

# Default sibling locations
DEFAULT_DATA = Path("e:/autoforensicai_data") if platform.system() == "Windows" else Path.home() / "autoforensicai_data"
DEFAULT_ALL = Path("e:/xiaokon-all") if platform.system() == "Windows" else Path.home() / "xiaokon-all"

# Files/dirs that come from FRAMEWORK side
FRAMEWORK_INCLUDES = [
    "tools/",
    "tests/",
    "docs/",
    "worklog/",
    "CHANGELOG.md",
    "README.md",
    ".gitignore",
]

# Files/dirs that come from DATA side
DATA_INCLUDES = [
    "knowledge/",
    "cases/",
    "search.py",
]

# Files at all-repo top level that we always overwrite from framework's worklog state
# (these never come from data side)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command, str-ify Paths."""
    cmd = [str(c) if isinstance(c, Path) else c for c in cmd]
    print(f"  $ {' '.join(cmd)}" + (f"  (cwd={cwd})" if cwd else ""))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check, capture_output=capture, text=True)


def die(msg: str, code: int = 1) -> None:
    print(f"\n[sync_xiaokon_all][FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def ensure_repo(path: Path, label: str) -> None:
    if not path.exists():
        die(f"{label} not found at {path}\n  → clone it first")
    if not (path / ".git").exists():
        die(f"{label} at {path} is not a git repo")


def is_clean(path: Path) -> bool:
    r = run(["git", "status", "--porcelain"], cwd=path, capture=True, check=False)
    return r.stdout.strip() == ""


def pull_main(path: Path, label: str) -> None:
    print(f"\n  [{label}] pulling latest...")
    if not is_clean(path):
        print(f"  ⚠ {label} working tree dirty — skipping pull")
        return
    run(["git", "pull", "--ff-only", "origin", "main"], cwd=path, check=False)


def copy_tree(src: Path, dst: Path, label: str = "") -> int:
    """Copy src dir/file to dst (overwriting), return file count copied."""
    count = 0
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    if not src.is_dir():
        return 0
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.pyc", ".cache", "node_modules"
    ))
    for _ in dst.rglob("*"):
        if _.is_file():
            count += 1
    return count


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-repo", type=Path, default=DEFAULT_DATA,
                    help=f"path to autoforensicai_data clone (default: {DEFAULT_DATA})")
    ap.add_argument("--all-repo", type=Path, default=DEFAULT_ALL,
                    help=f"path to xiaokon-all clone (default: {DEFAULT_ALL})")
    ap.add_argument("--dry-run", action="store_true", help="show what would be done, don't push")
    ap.add_argument("--no-pull", action="store_true", help="skip pulling latest from sources")
    ap.add_argument("--no-push", action="store_true", help="commit but don't push")
    args = ap.parse_args()

    framework = FRAMEWORK_ROOT
    data = args.data_repo
    allrepo = args.all_repo

    print(f"== sync_to_xiaokon_all ==")
    print(f"  framework: {framework}")
    print(f"  data:      {data}")
    print(f"  all:       {allrepo}")
    print()

    # Pre-check
    ensure_repo(framework, "framework")
    ensure_repo(data, "data")
    ensure_repo(allrepo, "all")

    # Pull latest sources
    if not args.no_pull:
        pull_main(framework, "framework")
        pull_main(data, "data")
        pull_main(allrepo, "all")

    # Verify all-repo is clean
    if not is_clean(allrepo):
        die(f"all-repo {allrepo} is dirty — commit/discard first")

    print(f"\n== Building union into {allrepo} ==")

    # 1. Remove old framework-side dirs that no longer exist in framework
    for inc in FRAMEWORK_INCLUDES:
        target = allrepo / inc.rstrip("/")
        # Only delete if framework has a placeholder (we'll rebuild from framework)
        # For simplicity, always remove + recopy
        if target.exists():
            remove_path(target)

    # 2. Copy framework-side
    fw_count = 0
    for inc in FRAMEWORK_INCLUDES:
        src = framework / inc.rstrip("/")
        dst = allrepo / inc.rstrip("/")
        if src.exists():
            n = copy_tree(src, dst)
            fw_count += n
            print(f"  ✓ {inc}: {n} files (from framework)")
        else:
            print(f"  - {inc}: not in framework, skip")

    # 3. Remove old data-side dirs
    for inc in DATA_INCLUDES:
        target = allrepo / inc.rstrip("/")
        if target.exists():
            remove_path(target)

    # 4. Copy data-side
    data_count = 0
    for inc in DATA_INCLUDES:
        src = data / inc.rstrip("/")
        dst = allrepo / inc.rstrip("/")
        if src.exists():
            n = copy_tree(src, dst)
            data_count += n
            print(f"  ✓ {inc}: {n} files (from data)")
        else:
            print(f"  - {inc}: not in data, skip")

    print(f"\n  Total: framework={fw_count} files, data={data_count} files")

    # 5. Check git status in all repo
    if is_clean(allrepo):
        print(f"\n== No changes — all repo already in sync ==")
        return 0

    # 6. Show diff stat
    print(f"\n== Changes in all repo ==")
    run(["git", "status", "--short"], cwd=allrepo, check=False)

    if args.dry_run:
        print(f"\n[DRY-RUN] would commit + push")
        return 0

    # 7. Commit
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = (f"sync: framework@{get_short_hash(framework)} + data@{get_short_hash(data)} "
           f"({stamp})")
    run(["git", "add", "-A"], cwd=allrepo)
    run(["git", "commit", "-m", msg], cwd=allrepo, check=False)

    # 8. Push
    if args.no_push:
        print(f"\n[--no-push] commit done, skipping push")
    else:
        print(f"\n== Pushing all → origin ==")
        run(["git", "push", "origin", "main"], cwd=allrepo, check=False)

    print(f"\n== DONE ==")
    return 0


def get_short_hash(repo: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo),
                          capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except Exception:
        return "?"


if __name__ == "__main__":
    sys.exit(main())
