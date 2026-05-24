"""Git-based collaboration sync."""

import subprocess
from pathlib import Path
from typing import Any, Dict

from ..core import now_str, load_yaml, save_yaml, shared_dir


def git_run(case_dir: str, *git_args: str) -> subprocess.CompletedProcess:
    """Run a git command in the case directory."""
    result = subprocess.run(
        ["git"] + list(git_args),
        cwd=case_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode != 0 and result.stderr:
        print(f"[git] {result.stderr.strip()}")
    return result


def sync_git_file(case_dir: str, fname: str) -> Dict[str, Any]:
    """Sync single file via Git."""
    case_dir = Path(case_dir)
    fpath = case_dir / "shared" / fname

    try:
        git_run(case_dir, "pull", "--rebase")
        result = git_run(case_dir, "status", "--porcelain", "shared/" + fname)
        if result.stdout.strip():
            return {"file": fname, "status": "success", "updated": True}
        else:
            return {"file": fname, "status": "success", "updated": False}
    except Exception as e:
        return {"file": fname, "status": "error", "message": str(e)}


def cmd_git_init(args):
    case_dir = Path(args.case_dir)
    shared = shared_dir(case_dir)

    if not (case_dir / ".git").exists():
        git_run(case_dir, "init")
        print("[+] Initialized git repo")

    gitignore = case_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Evidence files (too large for git)\n"
            "*.E01\n*.e01\n*.vmdk\n*.vhd\n*.dd\n*.raw\n*.zip\n"
            "*.bak\n"
            "mobile/backup/\n"
            "computer/mounted/\n"
            "server/vmdk_root/\n"
            "\n# Keep shared/ tracked\n"
            "!shared/\n",
            encoding="utf-8",
        )

    for fname in ["findings.yaml", "progress.yaml", "answers.yaml"]:
        fpath = shared / fname
        if not fpath.exists():
            save_yaml(fpath, [])

    if args.repo:
        git_run(case_dir, "remote", "add", "origin", args.repo)
        print(f"[+] Remote set to {args.repo}")

    git_run(case_dir, "add", "-A")
    git_run(case_dir, "commit", "-m", "init case workspace")
    print("[+] Case workspace initialized.")


def cmd_git_push(args):
    case_dir = args.case_dir
    git_run(case_dir, "add", "shared/")
    msg = args.message or f"sync {now_str()}"
    git_run(case_dir, "commit", "-m", msg)
    result = git_run(case_dir, "push")
    if result.returncode == 0:
        print(f"[+] Pushed: {msg}")
    else:
        print("[!] Push failed.")


def cmd_git_pull(args):
    result = git_run(args.case_dir, "pull", "--rebase")
    if result.returncode == 0:
        print("[+] Pulled latest changes")
    else:
        print("[!] Pull failed.")
