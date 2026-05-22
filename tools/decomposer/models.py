"""Data models for challenge decomposition.

SubGoal: A single unit of work in the decomposition plan.
DecompositionPlan: The complete decomposition output.
EvidenceInfo: Metadata about an evidence file (pre-computed once).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class SubGoalLevel:
    SHARED = 0     # Shared context (index, hash, type detect) — done ONCE
    PREP = 1       # Evidence prep (mount, extract, decrypt)
    ANALYSIS = 2   # Domain analysis (memory, disk, network, etc.)
    QUESTION = 3   # Direct question answering


@dataclass
class EvidenceInfo:
    """Metadata about a single evidence file."""
    path: str
    size_bytes: int
    extension: str
    detected_type: str = "unknown"   # memory/disk/network/mobile/binary/stego/crypto/log/unknown
    magic_bytes: str = ""
    mime_type: str = ""
    sha256: str = ""
    is_archive: bool = False
    is_encrypted: bool = False
    mount_required: bool = False
    children: List[str] = field(default_factory=list)


@dataclass
class SubGoal:
    """A single sub-goal in the decomposition plan."""
    id: str
    level: int
    description: str
    domain: str = ""               # computer/mobile/server/network/binary/stego/crypto
    task_type: str = ""            # matches smart_scheduler.TaskType values
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    assigned_role: str = ""
    estimated_minutes: int = 30
    priority: int = 3              # 1=highest, 3=normal, 5=low
    answer_format: str = ""
    question_text: str = ""


@dataclass
class DecompositionPlan:
    """The complete decomposition output for a challenge."""
    challenge_name: str
    challenge_description: str = ""
    created_at: str = ""
    evidence_files: List[EvidenceInfo] = field(default_factory=list)
    sub_goals: Dict[str, SubGoal] = field(default_factory=dict)
    topological_order: List[List[str]] = field(default_factory=list)
    critical_path: List[str] = field(default_factory=list)
    critical_path_minutes: int = 0
    role_assignments: Dict[str, List[str]] = field(default_factory=dict)
    tool_recommendations: Dict[str, List[str]] = field(default_factory=dict)
