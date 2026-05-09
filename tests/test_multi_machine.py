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

    print("\n--- safe_push ---")
    test_safe_push_help()

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
