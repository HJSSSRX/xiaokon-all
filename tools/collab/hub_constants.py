"""Constants shared across hub modules."""

import re
import threading

from ..core import next_seq_id, next_finding_id as _core_next_finding_id
from ..core import next_question_id, next_blocker_id, next_need_id

ROLE_PREFIX = {
    "computer_analyst": "C",
    "mobile_analyst": "M",
    "server_analyst": "S",
    "binary_analyst": "B",
    "main_designer": "D",
}

ROLE_TO_CATEGORY = {
    "computer_analyst": "computer_forensics",
    "mobile_analyst": "mobile_forensics",
    "server_analyst": "server_forensics",
    "binary_analyst": "binary_forensics",
    "internet_analyst": "internet_forensics",
}

FILE_WHITELIST = re.compile(
    r"^(role_prompt_\w+\.md|shared/[\w_-]+\.(yaml|md|jsonl)|[A-Z][A-Z0-9_]+\.md|README\.md|import_[\w_]+\.py)$"
)

_LOCK = threading.Lock()
_HUB_STARTED_AT = None

NEED_STATUS = ("open", "claimed", "fulfilled", "abandoned")
NEED_CONFIDENCE_5 = (
    "platform_confirmed",
    "self_verified_db",
    "cross_source_high",
    "single_source_high",
    "gui_observed",
    "placeholder",
)
NEED_CONFIDENCE_LEGACY = ("high", "medium", "low")


def next_finding_id(findings, role):
    """Generate finding ID with role-based prefix."""
    p = ROLE_PREFIX.get(role, "X")
    return _core_next_finding_id(findings, p)


def normalize_confidence(c: str) -> str:
    """Map legacy 3-level confidence to 5-level."""
    c = (c or "").strip().lower()
    if c in NEED_CONFIDENCE_5:
        return c
    legacy_map = {
        "high": "single_source_high",
        "medium": "gui_observed",
        "low": "placeholder",
    }
    return legacy_map.get(c, "placeholder")
