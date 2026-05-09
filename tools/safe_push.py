#!/usr/bin/env python3
"""
safe_push.py — One-command safe push to all three repos.

Workflow:
  1. Read MACHINE_ID (from setup_machine.py output)
  2. Verify clean working tree
  3. Network pre-check (tools/check_net.ps1 if Windows)
  4. Fetch all configured remotes
  5. Run tools/build_kb_index.py (rebuild INDEX, auto-commit if changed)
  6. Run tests (tests/run_all.py)
  7. Rebase onto origin/main
  8. Push to:  origin (framework) + data (knowledge) + all (full)
  9. Auto-abort + rollback on any failure

Usage:
  python tools/safe_push.py                     # full flow
  python tools/safe_push.py --dry-run           # show what would happen
  python tools/safe_push.py --no-test           # skip tests (NOT recommended)
  python tools/safe_push.py --only origin       # push only one remote
  python tools/safe_push.py --only origin,all   # push subset
  python tools/safe_push.py --skip-rebase       # if you know there's no remote drift

See: docs/MULTI_MACHINE_CONTRIBUTION.md
"""
from __future__ import annotations

import argparse
import os
import platform
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

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
import detect_layout  # noqa: E402

# Logical → git remote name mapping (default for layout A)
REMOTE_MAP = {
    "origin": "origin",   # framework
    "data":   "data",     # knowledge data
    "all":    "all",      # full monorepo
}


# ───── Helpers ─────

class Step:
    def __init__(self, n: int, title: str):
        self.n = n
        self.title = title

    def __enter__(self):
        print(f"\n== [{self.n}] {self.title} ==")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def die(msg: str, code: int = 1) -> None:
    print(f"\n[safe_push][FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str], check: bool = True, capture: bool = False, **kw) -> subprocess.CompletedProcess:
    if isinstance(cmd[0], Path):
        cmd[0] = str(cmd[0])
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, cwd=str(REPO_ROOT), **kw)


def read_machine_id() -> str:
    if platform.system() == "Windows":
        f = Path(os.environ.get("APPDATA", "")) / "autoforensicai" / "machine.txt"
    else:
        f = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autoforensicai" / "machine.txt"
    if not f.exists():
        die(f"machine.txt not found at {f}\n  → run: python tools/setup_machine.py")
    return f.read_text(encoding="utf-8").strip()


def is_clean() -> bool:
    r = run(["git", "status", "--porcelain"], capture=True)
    return r.stdout.strip() == ""


def list_remotes() -> set[str]:
    r = run(["git", "remote"], capture=True)
    return set(r.stdout.split())


def current_branch() -> str:
    r = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    return r.stdout.strip()


# ───── Steps ─────

def step_pre_check(args, mid: str):
    with Step(1, "PRE-CHECK"):
        # 1a. clean working tree
        if not is_clean():
            r = run(["git", "status", "--porcelain"], capture=True)
            print("  current dirty state:", file=sys.stderr)
            print(r.stdout, file=sys.stderr)
            die("working tree dirty — commit or stash first")

        # 1b. branch
        br = current_branch()
        if br not in ("main", "master"):
            die(f"not on main/master (currently on {br!r}); switch first")
        print(f"  ✓ on branch {br}, clean")

        # 1c. machine id
        print(f"  ✓ MACHINE_ID = {mid}")


def step_detect_layout(args) -> dict:
    """Detect repo layout — gates which targets we can safely push to."""
    with Step("1.5", "DETECT LAYOUT"):
        info = detect_layout.detect()
        print(f"  layout: {info['layout']}")
        print(f"  reason: {info['layout_reason']}")
        # Block dangerous push attempts unless --force-layout is passed
        unsafe_targets = [t for t, sa in info["push_safety"].items()
                          if not sa.get("safe") and sa.get("remote")]
        if unsafe_targets and not args.force_layout:
            print(f"\n  ⚠ Unsafe push targets in this layout: {unsafe_targets}")
            print(f"     This run will SKIP them automatically.")
            print(f"     Use --force-layout if you really know what you're doing.")
        return info


def step_network(args):
    with Step(2, "NETWORK"):
        if platform.system() != "Windows":
            print("  (non-Windows: skip)")
            return
        check_net = REPO_ROOT / "tools" / "check_net.ps1"
        if not check_net.exists():
            print("  (no check_net.ps1: skip)")
            return
        try:
            r = subprocess.run(
                ["powershell", "-File", str(check_net), "-Quiet"],
                cwd=str(REPO_ROOT), check=False,
            )
            if r.returncode == 0:
                print("  ✓ network clean")
            elif r.returncode == 1:
                print("  ⚠ DNS hijacked — will use schannel for pushes")
                args._sslopt = ["-c", "http.sslBackend=schannel"]
            else:
                die(f"network check failed (exit {r.returncode})")
        except Exception as e:
            print(f"  (check_net error: {e}, skipping)")


def step_fetch(args):
    with Step(3, "FETCH all remotes"):
        remotes = list_remotes()
        for logical, gr in REMOTE_MAP.items():
            if gr in remotes:
                run(["git", "fetch", gr], check=False)
                print(f"  ✓ fetched {gr}")
            else:
                print(f"  - {logical} ({gr}): not configured, skip")


def step_rebuild_index(args, mid: str):
    with Step(4, "REBUILD INDEX (auto)"):
        builder = REPO_ROOT / "tools" / "build_kb_index.py"
        if not builder.exists():
            print("  (no build_kb_index.py: skip)")
            return
        if args.dry_run:
            run([sys.executable, str(builder), "--dry-run"], check=False)
            return
        run([sys.executable, str(builder)], check=False)
        # If index changed, auto-commit
        if not is_clean():
            print("  → INDEX changed, auto-commit")
            run(["git", "add", "knowledge/"], check=False)
            run(["git", "commit", "-m", f"chore(index): auto-rebuild [machine: {mid}]"], check=False)


def step_test(args):
    if args.no_test:
        with Step(5, "TESTS (skipped via --no-test)"):
            return
    with Step(5, "TESTS"):
        runner = REPO_ROOT / "tests" / "run_all.py"
        if not runner.exists():
            print("  (no tests/run_all.py: skip)")
            return
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            r = subprocess.run(
                [sys.executable, str(runner)],
                cwd=str(REPO_ROOT), env=env, check=False,
            )
            if r.returncode != 0:
                die(f"tests failed (exit {r.returncode})")
            print("  ✓ all tests passed")
        except KeyboardInterrupt:
            die("interrupted")


def step_rebase(args):
    if args.skip_rebase:
        with Step(6, "REBASE (skipped)"):
            return
    with Step(6, "REBASE onto origin/<remote-branch>"):
        remotes = list_remotes()
        if "origin" not in remotes:
            print("  (no origin: skip rebase)")
            return
        # Try main first then master
        upstream = None
        for cand in (f"origin/main", f"origin/master"):
            r = run(["git", "rev-parse", "--verify", cand], capture=True, check=False)
            if r.returncode == 0:
                upstream = cand
                break
        if not upstream:
            print(f"  (no origin/main or origin/master: skip)")
            return
        # Check if remote ahead
        r = run(["git", "rev-list", "--count", f"HEAD..{upstream}"], capture=True, check=False)
        try:
            ahead = int(r.stdout.strip() or "0")
        except ValueError:
            ahead = 0
        if ahead == 0:
            print(f"  ✓ {upstream} has 0 commits ahead, no rebase needed")
            return
        print(f"  {upstream} is ahead by {ahead}, rebasing...")
        r = subprocess.run(
            ["git", "rebase", upstream], cwd=str(REPO_ROOT), check=False,
        )
        if r.returncode != 0:
            print("  ✗ rebase had conflicts. Resolve manually then run:")
            print("    git rebase --continue")
            print("    python tools/safe_push.py --skip-rebase")
            die(f"rebase failed")
        print("  ✓ rebased")


def step_push(args, mid: str, layout_info: dict):
    sslopt = getattr(args, "_sslopt", [])
    with Step(7, "PUSH"):
        local_branch = current_branch()
        # Each canonical target with its safety from detect_layout
        # safety[<canonical>] = {"safe": bool, "remote": <local_remote_name>, "reason": ...}
        safety = layout_info["push_safety"]

        # Map: canonical → (logical alias for --only filter)
        canonical_to_alias = {"framework": "origin", "data": "data", "all": "all"}

        # Decide what user wants to push
        if args.only:
            wanted_aliases = {a.strip() for a in args.only.split(",")}
        else:
            wanted_aliases = {"origin", "data", "all"}

        any_pushed = False
        any_skipped_unsafe = []
        for canonical, alias in canonical_to_alias.items():
            if alias not in wanted_aliases:
                continue
            sa = safety.get(canonical, {})
            remote = sa.get("remote")
            if not remote:
                print(f"  - {canonical}: remote not configured, skip")
                continue
            if not sa.get("safe") and not args.force_layout:
                any_skipped_unsafe.append(canonical)
                print(f"  ✗ {canonical} ({remote}): UNSAFE — {sa.get('reason')}")
                print(f"     skipped (use --force-layout to override)")
                continue

            # Build push refspec: local_branch:main (because remotes use 'main')
            refspec = f"{local_branch}:main" if local_branch != "main" else "main"
            cmd = ["git"] + sslopt + ["push", remote, refspec]
            if args.dry_run:
                print(f"  [DRY] would: {' '.join(cmd)}")
                continue
            r = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
            if r.returncode != 0:
                print(f"  ✗ push to {remote} failed", file=sys.stderr)
                # Auto-merge fallback for 'all' canonical
                if canonical == "all":
                    print(f"  → trying merge sync for {remote}...")
                    r2 = subprocess.run(["git", "fetch", remote], cwd=str(REPO_ROOT), check=False)
                    if r2.returncode == 0:
                        from datetime import datetime
                        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                        merge_msg = f"Merge {remote}/main (auto-sync {stamp}) [machine: {mid}]"
                        r3 = subprocess.run(
                            ["git", "merge", "--no-ff", f"{remote}/main", "-m", merge_msg],
                            cwd=str(REPO_ROOT), check=False,
                        )
                        if r3.returncode == 0:
                            r4 = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
                            if r4.returncode == 0:
                                print(f"  ✓ {canonical} ({remote}) pushed after merge sync")
                                any_pushed = True
                                continue
                            subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=str(REPO_ROOT), check=False)
                        else:
                            subprocess.run(["git", "merge", "--abort"], cwd=str(REPO_ROOT), check=False)
                            print(f"  ✗ merge had conflicts, aborted; resolve manually")
                continue
            print(f"  ✓ {canonical} ({remote}) pushed via {refspec}")
            any_pushed = True

        if any_skipped_unsafe:
            print(f"\n  Layout safety blocked: {any_skipped_unsafe}")
            print(f"  layout = {layout_info['layout']}")
            print(f"  See docs/MULTI_MACHINE_CONTRIBUTION.md for the right workflow.")

        if not any_pushed and not args.dry_run:
            die("no pushes succeeded")


# ───── Main ─────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show actions, don't push")
    ap.add_argument("--no-test", action="store_true", help="skip tests/run_all.py")
    ap.add_argument("--skip-rebase", action="store_true", help="skip rebase step")
    ap.add_argument("--only", type=str, help="comma-separated subset: origin,data,all")
    ap.add_argument("--force-layout", action="store_true",
                    help="bypass layout safety (push to remotes detect_layout flagged as unsafe)")
    args = ap.parse_args()

    print("== safe_push.py ==")
    mid = read_machine_id()

    step_pre_check(args, mid)
    layout_info = step_detect_layout(args)
    step_network(args)
    step_fetch(args)
    step_rebuild_index(args, mid)
    step_test(args)
    step_rebase(args)
    step_push(args, mid, layout_info)

    print(f"\n== DONE ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
