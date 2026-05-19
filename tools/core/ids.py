"""Centralized ID generation for all collaboration modules.

Consolidates _next_seq_id pattern that was duplicated across
collab_hub, collab_sync, and core/utils.
"""

import re
from typing import Dict, List


def next_seq_id(items: List[Dict], prefix: str, key: str = "id") -> str:
    """Generate next sequential ID for a list of dicts.

    Args:
        items: List of dicts with an ID field.
        prefix: ID prefix (e.g. "F", "Q", "B", "N").
        key: The dict key holding the ID string.

    Returns:
        Next ID like "F001", "Q002", etc.
    """
    pat = re.compile(rf"^{prefix}(\d+)$")
    nums = []
    for it in items:
        if isinstance(it, dict):
            m = pat.match(str(it.get(key, "")))
            if m:
                nums.append(int(m.group(1)))
    return f"{prefix}{max(nums, default=0) + 1:03d}"


def next_finding_id(findings: List[Dict], prefix: str = "X") -> str:
    """Generate next finding ID with optional role prefix."""
    return next_seq_id(findings, f"F-{prefix}")


def next_question_id(questions: List[Dict]) -> str:
    """Generate next question ID."""
    return next_seq_id(questions, "Q")


def next_blocker_id(blockers: List[Dict]) -> str:
    """Generate next blocker ID."""
    return next_seq_id(blockers, "B")


def next_need_id(needs: List[Dict]) -> str:
    """Generate next need ID."""
    return next_seq_id(needs, "N")
