"""ID generation and confidence normalization for hub."""

from ..core import next_seq_id, next_finding_id as _core_next_finding_id
from ..core import next_question_id, next_blocker_id, next_need_id
from .hub_constants import ROLE_PREFIX, NEED_CONFIDENCE_5, NEED_CONFIDENCE_LEGACY


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
