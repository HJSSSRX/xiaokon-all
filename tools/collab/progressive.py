"""Progressive sync strategy — layered synchronization by priority."""

import datetime
from typing import Any, Dict, List, Optional

from ..core import shared_dir
from .lan_sync import get_last_sync_time, sync_lan_file
from .git_sync import sync_git_file


SYNC_PRIORITIES: List[Dict[str, Any]] = [
    {"name": "answers", "file": "answers.yaml", "priority": 1, "sync_interval": 10},
    {"name": "findings", "file": "findings.yaml", "priority": 2, "sync_interval": 30},
    {"name": "progress", "file": "progress.yaml", "priority": 3, "sync_interval": 60},
    {"name": "questions", "file": "questions.yaml", "priority": 4, "sync_interval": 120},
    {"name": "session_log", "file": "session_log.yaml", "priority": 5, "sync_interval": 300},
    {"name": "blockers", "file": "blockers.yaml", "priority": 5, "sync_interval": 300},
    {"name": "strategy", "file": "strategy.yaml", "priority": 5, "sync_interval": 300},
]


def progressive_sync(case_dir: str, server: Optional[str] = None, mode: str = "lan") -> Dict[str, Any]:
    """Progressive synchronization by priority."""
    sd = shared_dir(case_dir)
    results = []

    for sync_item in SYNC_PRIORITIES:
        fname = sync_item["file"]
        priority = sync_item["priority"]

        try:
            last_sync = get_last_sync_time(case_dir, fname)
            if last_sync and priority >= 4:
                age = (datetime.datetime.now() - last_sync).total_seconds()
                if age < sync_item["sync_interval"]:
                    results.append({
                        "file": fname, "priority": priority,
                        "status": "success", "skipped": True,
                        "reason": "Recent sync",
                    })
                    continue

            if mode == "lan" and server:
                result = sync_lan_file(sd, fname, server)
            elif mode == "git":
                result = sync_git_file(case_dir, fname)
            else:
                result = {"status": "error", "file": fname, "message": "Unknown mode"}

            result["priority"] = priority
            results.append(result)

        except Exception as e:
            results.append({
                "file": fname, "priority": priority,
                "status": "error", "message": str(e),
            })

    summary = {
        "total": len(results),
        "success": sum(1 for r in results if r.get("status") == "success"),
        "failed": sum(1 for r in results if r.get("status") == "error"),
        "skipped": sum(1 for r in results if r.get("skipped")),
    }

    return {"results": results, "summary": summary}
