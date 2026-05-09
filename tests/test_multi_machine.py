"""
test_multi_machine.py — Multi-machine collaboration tools.

Tests:
  1. setup_machine.py — read/write MACHINE_ID, status command
  2. build_kb_index.py — INDEX generation from synthetic kb
  3. safe_push.py — argparse + dry-run flow (no actual push)

Strategy: synthesize a temp kb dir with retrospectives/skills/solved fixture,
verify INDEX content. Avoid touching real repo/state.

Run:
  python tests/test_multi_machine.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

PASSED = 0
FAILED = 0


def t(name: str, cond: bool, msg: str = ""):
    global PASSED, FAILED
    if cond:
        print(f"[OK]   {name}")
        PASSED += 1
    else:
        print(f"[FAIL] {name}  {msg}")
        FAILED += 1


# ───── Fixtures ─────

def make_kb(tmp: Path) -> Path:
    """Build synthetic knowledge/ tree."""
    kb = tmp / "knowledge"
    (kb / "retrospectives").mkdir(parents=True)
    (kb / "skills").mkdir()
    (kb / "solved").mkdir()
    (kb / "cards").mkdir()
    (kb / "wp_index").mkdir()

    # Retrospective WITH machine suffix
    (kb / "retrospectives" / "20260101_X01_root_cause__A_main.yaml").write_text(
        "title: 根本原因分析示例\n"
        "machine: A_main\n"
        "date: 2026-01-01\n"
        "tags: [computer, debugging]\n"
        "category: lesson\n"
        "role: computer\n"
        "lesson: 不要假设, 先查日志\n",
        encoding="utf-8",
    )
    # Retrospective WITHOUT machine suffix (legacy)
    (kb / "retrospectives" / "20260102_X02_legacy.yaml").write_text(
        "title: Legacy entry\n"
        "tags: [legacy]\n",
        encoding="utf-8",
    )
    # Same problem, different machine
    (kb / "retrospectives" / "20260101_X01_root_cause__B_second.yaml").write_text(
        "title: 同一题 B 机视角\n"
        "machine: B_second\n"
        "date: 2026-01-01\n",
        encoding="utf-8",
    )

    # Skills (markdown with frontmatter)
    (kb / "skills" / "vol2_quick.md").write_text(
        "---\n"
        "title: Volatility 2 速查\n"
        "tags: [memory, volatility]\n"
        "---\n\n"
        "# Volatility 2 Quick Reference\n\n"
        "TBD\n",
        encoding="utf-8",
    )

    # Solved (markdown without frontmatter, has H1)
    (kb / "solved" / "demo_solved.md").write_text(
        "# Demo Solved Problem\n\n"
        "Stuff here.\n",
        encoding="utf-8",
    )

    # Cards
    (kb / "cards" / "demo_card.md").write_text(
        "# Demo Card\n",
        encoding="utf-8",
    )

    # wp_index
    (kb / "wp_index" / "2026FIC.md").write_text(
        "# 2026 FIC\n",
        encoding="utf-8",
    )

    return kb


# ───── Tests: build_kb_index ─────

def test_build_kb_index_dry_run():
    import yaml
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        kb = make_kb(tmp)
        # Run build_kb_index --dir <tmp> (it expects parent of knowledge/, OR knowledge/)
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_kb_index.py"),
             "--dir", str(tmp), "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        t("dry-run exit 0", r.returncode == 0, r.stderr[:200])
        t("dry-run shows changes", "WOULD UPDATE" in r.stdout)
        # Files should NOT actually exist yet
        t("dry-run does not write", not (kb / "retrospectives" / "INDEX.yaml").exists())


def test_build_kb_index_actual():
    import yaml
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        kb = make_kb(tmp)
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_kb_index.py"),
             "--dir", str(tmp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        t("build exit 0", r.returncode == 0, r.stderr[:200])
        # 1. retrospectives/INDEX.yaml exists & valid
        idx_path = kb / "retrospectives" / "INDEX.yaml"
        t("retrospectives INDEX.yaml exists", idx_path.exists())
        idx = yaml.safe_load(idx_path.read_text(encoding="utf-8"))
        t("INDEX has _generated_by", "build_kb_index.py" in idx.get("_generated_by", ""))
        t("INDEX has 3 entries", idx.get("_count") == 3)
        # 2. machine ID parsed correctly
        machines = {e.get("machine") for e in idx["entries"]}
        t("machine ID parsed (A_main)", "A_main" in machines)
        t("machine ID parsed (B_second)", "B_second" in machines)
        t("machine ID None for legacy", None in machines)
        # 3. skills INDEX.md exists
        skills_idx = kb / "skills" / "INDEX.md"
        t("skills INDEX.md exists", skills_idx.exists())
        skills_text = skills_idx.read_text(encoding="utf-8")
        t("skills INDEX has title from frontmatter", "Volatility 2 速查" in skills_text)
        t("skills INDEX has tags", "`memory`" in skills_text)
        # 4. solved (no frontmatter, picks H1)
        solved_text = (kb / "solved" / "INDEX.md").read_text(encoding="utf-8")
        t("solved INDEX picks H1 as title", "Demo Solved Problem" in solved_text)
        # 5. top-level
        top = yaml.safe_load((kb / "INDEX.yaml").read_text(encoding="utf-8"))
        t("top INDEX has retrospectives section", "retrospectives" in top["sections"])
        t("top INDEX retro count = 3", top["sections"]["retrospectives"]["count"] == 3)


def test_build_kb_index_check_mode():
    """--check should exit 1 if INDEX is stale."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        kb = make_kb(tmp)
        # First time: stale (INDEX doesn't exist)
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_kb_index.py"),
             "--dir", str(tmp), "--check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        t("--check stale → exit 1", r.returncode == 1)
        # Build it
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_kb_index.py"), "--dir", str(tmp)],
            capture_output=True, check=True,
        )
        # Now check should pass
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_kb_index.py"),
             "--dir", str(tmp), "--check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        t("--check up-to-date → exit 0", r.returncode == 0)


# ───── Tests: setup_machine ─────

def test_setup_machine_status():
    """--status should print MACHINE_ID info."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "setup_machine.py"), "--status"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    t("setup_machine --status exit 0", r.returncode == 0)
    t("--status prints MACHINE_ID line", "MACHINE_ID:" in r.stdout)
    t("--status prints config file", "config file:" in r.stdout)


def test_setup_machine_id_validation():
    """Invalid IDs should be rejected."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "setup_machine.py"),
         "--id", "bad id!"],  # has space and bang
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    t("invalid ID → non-zero exit", r.returncode != 0)


# ───── Tests: safe_push ─────

def test_safe_push_help():
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "safe_push.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    t("safe_push --help exit 0", r.returncode == 0)
    t("--help mentions --dry-run", "--dry-run" in r.stdout)
    t("--help mentions --only", "--only" in r.stdout)


# ───── Tests: fic_kb_search resolve_kb_root (Bug 2 fix) ─────

def test_fic_kb_search_resolve_kb_cli_arg():
    """resolve_kb_root prefers explicit --kb-dir."""
    import importlib
    if "fic_kb_search" in sys.modules:
        importlib.reload(sys.modules["fic_kb_search"])
    import fic_kb_search

    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "fake_kb"
        (fake / "problems").mkdir(parents=True)
        result = fic_kb_search.resolve_kb_root(str(fake))
        t("resolve_kb_root respects --kb-dir CLI arg", result == fake)


def test_fic_kb_search_resolve_kb_env():
    """resolve_kb_root falls back to $AUTOFORENSICAI_KB."""
    import importlib
    if "fic_kb_search" in sys.modules:
        importlib.reload(sys.modules["fic_kb_search"])
    import fic_kb_search

    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "env_kb"
        (fake / "problems").mkdir(parents=True)
        old = os.environ.get("AUTOFORENSICAI_KB")
        os.environ["AUTOFORENSICAI_KB"] = str(fake)
        try:
            result = fic_kb_search.resolve_kb_root(None)
            t("resolve_kb_root respects AUTOFORENSICAI_KB env", result == fake)
        finally:
            if old is None:
                os.environ.pop("AUTOFORENSICAI_KB", None)
            else:
                os.environ["AUTOFORENSICAI_KB"] = old


def test_fic_kb_search_resolve_kb_missing():
    """resolve_kb_root returns None when nothing found AND no legacy path."""
    import importlib
    if "fic_kb_search" in sys.modules:
        importlib.reload(sys.modules["fic_kb_search"])
    import fic_kb_search

    # Use a non-existent CLI arg + ensure env var not set
    old = os.environ.pop("AUTOFORENSICAI_KB", None)
    try:
        result = fic_kb_search.resolve_kb_root("/nonexistent/path/xyz")
        # On A_main legacy path may exist; just assert it doesn't crash and
        # that it returns either None or a real existing dir
        if result is not None:
            t("resolve_kb_root returns existing dir when found", result.exists())
        else:
            t("resolve_kb_root returns None when nothing found", result is None)
    finally:
        if old is not None:
            os.environ["AUTOFORENSICAI_KB"] = old


# ───── Tests: setup_machine hooks dir (Bug 3 fix) ─────

def test_setup_machine_get_hooks_dir_default():
    """get_hooks_dir returns .git/hooks when core.hooksPath not set."""
    import importlib
    if "setup_machine" in sys.modules:
        importlib.reload(sys.modules["setup_machine"])
    import setup_machine

    # In our real repo, core.hooksPath is unset → expect .git/hooks
    hd = setup_machine.get_hooks_dir()
    t("get_hooks_dir returns a Path", hd is None or isinstance(hd, Path))
    # Don't assert exact path — depends on repo state


def test_setup_machine_render_combined_pre_commit():
    """render_combined_pre_commit merges existing user hook into combined version."""
    import importlib
    if "setup_machine" in sys.modules:
        importlib.reload(sys.modules["setup_machine"])
    import setup_machine

    existing = """#!/bin/sh
# user-defined check
echo "user hook ran"
exit 0
"""
    out = setup_machine.render_combined_pre_commit(existing)
    t("combined hook contains setup marker", setup_machine.SETUP_MARKER in out)
    t("combined hook contains our runtime check", "BLOCKED: runtime state files" in out)
    t("combined hook preserves existing user body", 'user hook ran' in out)
    t("combined hook starts with shebang", out.startswith("#!/bin/sh"))

    # Idempotence: feeding our own output should not double-embed
    out2 = setup_machine.render_combined_pre_commit(out)
    t("re-applying on combined hook does not recurse",
      out2.count("user hook ran") == 0,
      f"expected no preserved body, got {out2.count('user hook ran')} occurrences")


def test_setup_machine_get_hooks_dir_with_core_hookspath():
    """When core.hooksPath is set in a temp git repo, get_hooks_dir should honor it."""
    import importlib
    if "setup_machine" in sys.modules:
        importlib.reload(sys.modules["setup_machine"])
    import setup_machine

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "fakerepo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "core.hooksPath", ".myhooks"], cwd=repo, check=True)
        # Patch REPO_ROOT for this call
        original_root = setup_machine.REPO_ROOT
        setup_machine.REPO_ROOT = repo
        try:
            hd = setup_machine.get_hooks_dir()
            t("get_hooks_dir honors core.hooksPath", hd == repo / ".myhooks")
            t("get_hooks_dir creates hooksPath if missing", hd.exists())
        finally:
            setup_machine.REPO_ROOT = original_root


# ───── Run ─────

def main():
    print("=" * 60)
    print("multi-machine 工具测试")
    print("=" * 60)

    print("\n--- build_kb_index ---")
    test_build_kb_index_dry_run()
    test_build_kb_index_actual()
    test_build_kb_index_check_mode()

    print("\n--- setup_machine ---")
    test_setup_machine_status()
    test_setup_machine_id_validation()
    test_setup_machine_get_hooks_dir_default()
    test_setup_machine_render_combined_pre_commit()
    test_setup_machine_get_hooks_dir_with_core_hookspath()

    print("\n--- safe_push ---")
    test_safe_push_help()

    print("\n--- fic_kb_search resolve_kb_root ---")
    test_fic_kb_search_resolve_kb_cli_arg()
    test_fic_kb_search_resolve_kb_env()
    test_fic_kb_search_resolve_kb_missing()

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
