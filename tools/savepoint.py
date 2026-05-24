"""Crash-safety savepoint: auto-commits uncommitted changes as git safety points.

Run manually or schedule periodically. Each savepoint is a regular commit
that can be squashed/reset later.

Usage:
    python tools/savepoint.py           # commit if changes exist
    python tools/savepoint.py --status  # just report, don't commit
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          cwd=cwd or str(_REPO_ROOT), timeout=30)


def auto_savepoint(repo=None, dry_run=False):
    repo = repo or str(_REPO_ROOT)
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Working directory
    r = _run(["git", "status", "--porcelain"], cwd=repo)
    if r.returncode != 0:
        print(f"[savepoint] git status failed: {r.stderr.strip()}")
        return False

    changed = [l for l in r.stdout.splitlines() if l.strip()]
    if not changed:
        print(f"[savepoint] {dt}  clean — nothing to commit")
        return True

    n_files = len(changed)
    staged = sum(1 for l in changed if l[0] in "MADRC")
    untracked = sum(1 for l in changed if l.startswith("??"))

    print(f"[savepoint] {dt}  {n_files} files ({staged} modified, {untracked} new)")

    if dry_run:
        return True

    # Stage everything
    r = _run(["git", "add", "-A"], cwd=repo)
    if r.returncode != 0:
        print(f"[savepoint] git add failed: {r.stderr.strip()}")
        return False

    # Commit
    msg = f"safety: auto-savepoint [{n_files} files]"
    r = _run(["git", "commit", "-m", msg], cwd=repo)
    if r.returncode != 0:
        print(f"[savepoint] commit failed: {r.stderr.strip()}")
        return False

    print(f"[savepoint] committed: {r.stdout.splitlines()[0] if r.stdout.splitlines() else 'ok'}")
    return True


if __name__ == "__main__":
    dry = "--status" in sys.argv or "--dry-run" in sys.argv
    auto_savepoint(dry_run=dry)
