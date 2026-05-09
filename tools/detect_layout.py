#!/usr/bin/env python3
"""
detect_layout.py — Detect this machine's repo layout.

Two known layouts:

  LAYOUT_A "three independent clones" (used by A_main):
    - cwd is a framework-only clone (no knowledge/, no cases/)
    - sibling dirs hold data clone and all clone
    - remotes typically: origin = framework_url

  LAYOUT_B "monorepo with multiple remotes" (used by some user machines):
    - cwd is one git checkout that has knowledge/ + cases/ + tools/
    - remotes hold all three: framework / data / xiaokon-all
    - direct push to framework or data remote would CORRUPT them

Output: prints a JSON-friendly summary.
Exit code: 0 if a valid layout, 1 if unknown/broken.

Usage:
  python tools/detect_layout.py
  python tools/detect_layout.py --json
  python tools/detect_layout.py --quiet  # only exit code
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Known canonical URL fragments (already lowercase to match normalize_url)
URL_FRAMEWORK = "github.com/hjsssrx/xiaokon_autoforensicai"
URL_DATA = "github.com/hjsssrx/autoforensicai_data"
URL_ALL = "github.com/hjsssrx/xiaokon-all"


def run_git(args: list[str], cwd: Path | None = None, check: bool = False) -> str:
    """Return stdout text. Empty string on failure."""
    target = cwd if cwd is not None else REPO_ROOT
    try:
        r = subprocess.run(
            ["git"] + args, cwd=str(target),
            capture_output=True, text=True, check=check,
        )
        return r.stdout
    except Exception:
        return ""


def normalize_url(url: str) -> str:
    """Strip protocol/auth/.git so we can compare."""
    u = url.strip().lower()
    for prefix in ("https://", "http://", "git@", "ssh://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    u = u.replace(":", "/")  # git@github.com:HJSSSRX → github.com/HJSSSRX
    if u.endswith(".git"):
        u = u[:-4]
    return u


def list_remotes() -> dict[str, str]:
    """Return {remote_name: fetch_url}."""
    out = run_git(["remote", "-v"])
    remotes: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "(fetch)":
            remotes[parts[0]] = parts[1]
    return remotes


def classify_remote(url: str) -> str:
    """Return 'framework' | 'data' | 'all' | 'unknown'."""
    n = normalize_url(url)
    if URL_FRAMEWORK in n:
        return "framework"
    if URL_DATA in n:
        return "data"
    if URL_ALL in n:
        return "all"
    return "unknown"


def repo_has(rel: str) -> bool:
    """True iff git repo TRACKS at least one file under rel/.
    Uses git ls-files to ignore untracked/.gitignore'd leftovers.
    """
    out = run_git(["ls-files", rel])
    return bool(out.strip())


def current_branch() -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()


def is_inside_git() -> bool:
    return run_git(["rev-parse", "--is-inside-work-tree"]).strip() == "true"


def detect() -> dict:
    info: dict = {
        "cwd": str(REPO_ROOT),
        "is_git": False,
        "branch": "",
        "remotes": {},
        "remotes_classified": {},
        "has_tools": repo_has("tools"),
        "has_tests": repo_has("tests"),
        "has_docs": repo_has("docs"),
        "has_knowledge": repo_has("knowledge"),
        "has_cases": repo_has("cases"),
        "layout": "unknown",
        "layout_reason": "",
        "push_safety": {},
        "recommendations": [],
    }

    if not is_inside_git():
        info["layout"] = "not_a_git_repo"
        info["layout_reason"] = "cwd is not inside a git work tree"
        return info

    info["is_git"] = True
    info["branch"] = current_branch()

    remotes = list_remotes()
    info["remotes"] = remotes
    classified = {n: classify_remote(u) for n, u in remotes.items()}
    info["remotes_classified"] = classified

    # Aggregate: which canonical repos are reachable?
    canonical_present = set(classified.values()) - {"unknown"}

    # Decide layout — primary signal: origin url + content shape
    fw = info["has_tools"] and info["has_tests"] and info["has_docs"]
    kb = info["has_knowledge"] and info["has_cases"]
    origin_class = classified.get("origin", "unknown")

    # Layout B: monorepo + all 3 canonical urls as remotes (irrespective of origin name)
    if {"framework", "data", "all"}.issubset(canonical_present) and fw and kb:
        info["layout"] = "B_monorepo_multi"
        info["layout_reason"] = (
            "all 3 canonical repos are configured as remotes AND local has full monorepo content. "
            "This is a single working tree shared with framework+data+all remotes — "
            "direct push to framework/data remote would CORRUPT them."
        )
    # Layout A: clean single-purpose clones (origin tells us which one)
    elif origin_class == "framework" and fw and not kb:
        info["layout"] = "A_framework_clone"
        info["layout_reason"] = "origin = framework, local has framework-shaped content"
    elif origin_class == "framework" and fw and kb:
        info["layout"] = "A_framework_clone_legacy"
        info["layout_reason"] = (
            "origin = framework BUT local has knowledge/cases — "
            "pre-v0.5.3 layout, knowledge/cases should be moved to data repo"
        )
    elif origin_class == "data" and kb and not fw:
        info["layout"] = "A_data_clone"
        info["layout_reason"] = "origin = data, local has data-shaped content"
    elif origin_class == "data" and fw and kb:
        info["layout"] = "A_data_clone_with_extras"
        info["layout_reason"] = "origin = data but local has tools/tests too (was full clone of all repo perhaps)"
    elif origin_class == "all" and fw and kb:
        info["layout"] = "A_all_clone"
        info["layout_reason"] = "origin = xiaokon-all (monorepo), full content present"
    elif origin_class == "all":
        info["layout"] = "A_all_clone_partial"
        info["layout_reason"] = "origin = xiaokon-all but content is partial"
    else:
        info["layout"] = "unknown"
        info["layout_reason"] = (
            f"origin_class={origin_class!r}, fw={fw}, kb={kb}, "
            f"canonical_present={sorted(canonical_present)}"
        )

    # Push safety matrix:
    #   For each canonical target, can we safely git push <remote> <branch>?
    info["push_safety"] = compute_push_safety(info, classified)

    # Recommendations
    info["recommendations"] = build_recommendations(info)

    return info


def compute_push_safety(info: dict, classified: dict[str, str]) -> dict[str, dict]:
    """For each canonical target, decide if direct git push is safe."""
    safety: dict[str, dict] = {}
    layout = info["layout"]
    fw = info["has_tools"] and info["has_tests"] and info["has_docs"]
    kb = info["has_knowledge"] and info["has_cases"]

    for canonical in ("framework", "data", "all"):
        # Find which local remote name maps to this
        remote_names = [n for n, c in classified.items() if c == canonical]
        if not remote_names:
            safety[canonical] = {"safe": False, "reason": "remote not configured"}
            continue
        remote = remote_names[0]

        if canonical == "framework":
            # Safe to push if local content is FRAMEWORK-shaped
            if fw and not kb:
                safety[canonical] = {"safe": True, "remote": remote, "reason": "local matches framework shape"}
            elif fw and kb:
                safety[canonical] = {
                    "safe": False, "remote": remote,
                    "reason": "DANGER: local has knowledge/cases — direct push would inject them into framework repo. Use sync_to_xiaokon_all-style splitter instead.",
                }
            else:
                safety[canonical] = {"safe": False, "remote": remote, "reason": "local is missing tools/tests/docs"}
        elif canonical == "data":
            if kb and not fw:
                safety[canonical] = {"safe": True, "remote": remote, "reason": "local matches data shape"}
            elif fw and kb:
                safety[canonical] = {
                    "safe": False, "remote": remote,
                    "reason": "DANGER: local has tools/tests/docs — direct push would inject framework code into data repo.",
                }
            else:
                safety[canonical] = {"safe": False, "remote": remote, "reason": "local is missing knowledge/cases"}
        elif canonical == "all":
            # all = monorepo, safe to push only if local IS monorepo-shaped
            if fw and kb:
                safety[canonical] = {"safe": True, "remote": remote, "reason": "local is monorepo-shaped"}
            else:
                safety[canonical] = {
                    "safe": False, "remote": remote,
                    "reason": "local is partial — pushing would shrink the monorepo",
                }
    return safety


def build_recommendations(info: dict) -> list[str]:
    recs: list[str] = []
    layout = info["layout"]

    if layout == "A_framework_clone":
        recs.append("✓ This is a clean framework-only clone (A_main style).")
        recs.append("  Sibling clones expected at ../autoforensicai_data and ../xiaokon-all.")
        recs.append("  Use safe_push.py for framework, data clone for data, sync_to_xiaokon_all.py for all.")
    elif layout == "A_data_clone":
        recs.append("✓ This is a data-only clone.")
        recs.append("  Edit knowledge/ + cases/, then: git add -A && git commit && git push origin main")
        recs.append("  Run build_kb_index.py first if you added retrospectives/.")
    elif layout == "A_all_clone":
        recs.append("✓ This is a xiaokon-all monorepo clone.")
        recs.append("  This is a SINK repo: pulling is safe, but never push framework/data slices from here.")
        recs.append("  If you want to contribute, switch to a framework or data clone.")
    elif layout == "B_monorepo_multi":
        recs.append("⚠ Single working tree with 3 remotes (framework / data / all).")
        recs.append("  DANGER: direct `git push framework main` or `git push data main` will CORRUPT those repos.")
        recs.append("  Allowed pushes: ONLY xiaokon-all remote (it's the monorepo sink).")
        recs.append("  To split contributions to framework/data, ask the main coordinator (A_main) to do it.")
        recs.append("  Suggested workflow:")
        recs.append("    1. git pull <xiaokon-all-remote> main         # get latest")
        recs.append("    2. edit files normally")
        recs.append("    3. git push <xiaokon-all-remote> <local-branch>:main   # only this is safe")
    elif layout == "A_framework_clone_legacy":
        recs.append("⚠ Pre-v0.5.3 layout: framework clone but contains knowledge/cases.")
        recs.append("  Migration: move knowledge/ + cases/ to a separate data clone, then `git rm -r knowledge cases`.")
    elif layout == "B_partial_multi":
        recs.append(f"⚠ Partial multi-remote setup ({info['layout_reason']}).")
        recs.append("  Add the missing canonical remote, or simplify to single-purpose clone.")
    else:
        recs.append("✗ Cannot determine layout safely. Run with --json to inspect details.")

    # Branch warning
    if info["branch"] not in ("main", "master", ""):
        recs.append(f"  Note: current branch is {info['branch']!r}, remote branches are likely 'main'.")

    return recs


def format_human(info: dict) -> str:
    lines = []
    lines.append("== detect_layout ==")
    lines.append(f"  cwd:    {info['cwd']}")
    lines.append(f"  is_git: {info['is_git']}")
    lines.append(f"  branch: {info['branch']!r}")
    lines.append("")
    lines.append("  Content:")
    lines.append(f"    tools/       {'✓' if info['has_tools'] else '✗'}")
    lines.append(f"    tests/       {'✓' if info['has_tests'] else '✗'}")
    lines.append(f"    docs/        {'✓' if info['has_docs'] else '✗'}")
    lines.append(f"    knowledge/   {'✓' if info['has_knowledge'] else '✗'}")
    lines.append(f"    cases/       {'✓' if info['has_cases'] else '✗'}")
    lines.append("")
    lines.append("  Remotes:")
    if not info["remotes"]:
        lines.append("    (none)")
    else:
        for name, url in info["remotes"].items():
            cls = info["remotes_classified"].get(name, "?")
            lines.append(f"    {name:12s} → {cls:10s} ({url})")
    lines.append("")
    lines.append(f"  LAYOUT: {info['layout']}")
    lines.append(f"  Reason: {info['layout_reason']}")
    lines.append("")
    lines.append("  Push safety per canonical target:")
    for tgt, sa in info["push_safety"].items():
        mark = "✓" if sa.get("safe") else "✗"
        rem = sa.get("remote", "-")
        lines.append(f"    {mark} {tgt:10s} (remote={rem}): {sa['reason']}")
    lines.append("")
    lines.append("  Recommendations:")
    for r in info["recommendations"]:
        lines.append(f"    {r}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="output JSON")
    ap.add_argument("--quiet", action="store_true", help="silent, only exit code")
    args = ap.parse_args()

    info = detect()

    if args.quiet:
        pass
    elif args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print(format_human(info))

    # Exit code
    bad_layouts = {"unknown", "not_a_git_repo"}
    return 1 if info["layout"] in bad_layouts else 0


if __name__ == "__main__":
    sys.exit(main())
