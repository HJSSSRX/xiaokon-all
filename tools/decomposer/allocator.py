"""Allocation mode — automatically decides BOOST vs FOCUSED per sub-goal.

9-dimension weighted scoring + KB exact match override + dynamic priority
adjustment when boost fails.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from tools.decomposer.models import SubGoal, SubGoalLevel


class AllocationMode(Enum):
    BOOST = "boost"
    FOCUSED = "focused"


# Expert tools that signal high-complexity forensic work
_EXPERT_TOOLS = {
    "volatility3", "vol", "jadx", "ida", "ghidra", "openssl", "gpg",
    "hashcat", "wireshark", "tshark", "sqlmap", "objdump", "readelf",
    "apktool", "binwalk", "ewfmount", "fls", "icat",
}

# Universal tools: always present in ALL domains (FCA equivalence class #1, 100% support).
# These provide zero discriminatory signal for allocation decisions — strip before scoring.
_UNIVERSAL_TOOLS = {
    "competition:answer_diff", "competition:answer_format", "competition:question_parser",
    "core:cache", "core:config", "core:http_base", "core:id_gen", "core:yaml_utils",
    "hub:findings", "hub:http_server", "hub:role_log",
    "kb:feeder_crawl", "kb:kb_build", "kb:kb_search", "kb:kb_sync", "kb:tag_engine",
}
_UNIVERSAL_PREFIXES = ("competition:", "core:", "hub:", "kb:")

# Co-occurrence classes from FCA equivalence analysis.
# When one member is detected, the entire class is implied (always used together).
# Used to infer hidden complexity — if you see one, you're doing the whole class.
_COOCCURRENCE_CLASSES = [
    {  # Class 2: CTF automation toolchain (web + misc domains)
        "members": {"feeder:ctf_patterns", "feeder:ctf_recognizer", "feeder:ctf_coordinator",
                     "feeder:ctf_scanner", "feeder:blind_sqli", "feeder:flag_submit",
                     "feeder:spa_crawler", "feeder:skill_gen"},
        "complexity_boost": 0.15,  # moderate — these are semi-automated
    },
    {  # Class 3: Server virtualization forensics (server domain only)
        "members": {"forensics:vmdk_reader", "forensics:zfs_analysis", "integration:huoyan_mcp"},
        "complexity_boost": 0.25,  # high — enterprise virtualization stack
    },
    {  # Class 4: Network propagation analysis (network domain only)
        "members": {"analytics:propagation", "integration:remote_alive"},
        "complexity_boost": 0.10,  # low-moderate
    },
    {  # Class 5: Packet capture pipeline (network + server domains)
        "members": {"pcap:pcap_analysis", "pcap:flow_recon", "pcap:protocol_dissection"},
        "complexity_boost": 0.15,
    },
]

# Implication basis from FCA: when premise holds, conclusion is logically guaranteed.
# Used for pre-allocation hints.
_IMPLICATIONS = [
    # Rule 2: vision:ocr_engine + core tools => analytics:apriori + analytics:ncd
    {
        "premise": {"vision:ocr_engine"},
        "conclusion": {"analytics:apriori", "analytics:ncd"},
        "support": 0.182,
    },
]

# Single-domain tools: only 1 domain uses them → deterministic role assignment.
_SINGLE_DOMAIN_TOOLS = {
    "forensics:e01_reader": "computer",
    "forensics:vmdk_reader": "server",
    "forensics:zfs_analysis": "server",
    "integration:huoyan_mcp": "server",
    "integration:cloudflared_tunnel": "cloud",
    "integration:remote_alive": "network",
    "analytics:propagation": "network",
    "vision:mindmap_parser": "stego_crypto",
}


@dataclass
class AllocationConfig:
    """Tunable weights and thresholds for the allocator."""

    weight_level: float = 2.5
    weight_domain: float = 2.0
    weight_tools: float = 1.5
    weight_estimated_minutes: float = 1.5
    weight_task_type: float = 1.0
    weight_critical_path: float = 1.0
    weight_dependencies: float = 0.5
    weight_inputs: float = 0.5
    weight_dep_findings: float = 0.5

    boost_threshold: float = 0.40
    kb_exact_match_overrides: bool = True
    kb_match_threshold: int = 3

    @property
    def total_weight(self) -> float:
        return (
            self.weight_level + self.weight_domain + self.weight_tools +
            self.weight_estimated_minutes + self.weight_task_type +
            self.weight_critical_path + self.weight_dependencies +
            self.weight_inputs + self.weight_dep_findings
        )


@dataclass
class AllocationResult:
    sg_id: str
    mode: AllocationMode
    complexity_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    kb_match_found: bool = False
    kb_match_file: str = ""
    overridden: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "sg_id": self.sg_id,
            "mode": self.mode.value,
            "complexity_score": self.complexity_score,
            "dimension_scores": self.dimension_scores,
            "kb_match_found": self.kb_match_found,
            "kb_match_file": self.kb_match_file,
            "overridden": self.overridden,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AllocationResult":
        return cls(
            sg_id=data.get("sg_id", ""),
            mode=AllocationMode(data.get("mode", "focused")),
            complexity_score=data.get("complexity_score", 0.0),
            dimension_scores=data.get("dimension_scores", {}),
            kb_match_found=data.get("kb_match_found", False),
            kb_match_file=data.get("kb_match_file", ""),
            overridden=data.get("overridden", False),
            reason=data.get("reason", ""),
        )


@dataclass
class AllocationPlan:
    challenge_name: str
    allocations: Dict[str, AllocationResult] = field(default_factory=dict)
    summary: Dict[str, int] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# Dimension Scorers (each returns 0.0 = trivial to 1.0 = expert)
# ═══════════════════════════════════════════════════════════════════

def _score_level(level: int) -> float:
    return {0: 0.00, 1: 0.20, 2: 0.60, 3: 0.90}.get(level, 0.50)


def _score_domain(domain: str) -> float:
    """Score domain specialization level. Higher = more specialized / harder to automate."""
    scores = {
        "log": 0.10, "log_analysis": 0.10,
        "disk": 0.20, "disk_analysis": 0.20, "data_recovery": 0.20,
        "": 0.30, "general": 0.30,
        "registry": 0.30, "pcap": 0.30,
        "network": 0.40, "network_analysis": 0.40, "network_forensics": 0.40,
        "traffic": 0.40, "database": 0.40,
        "memory": 0.50, "memory_analysis": 0.50, "memory_forensics": 0.50,
        "web": 0.50, "web_pentest": 0.50, "sqli": 0.50, "xss": 0.50,
        "computer": 0.50, "computer_forensics": 0.50,
        "container": 0.60, "encoding": 0.60,
        "mobile": 0.70, "mobile_forensics": 0.70,
        "stego": 0.70, "stego_analysis": 0.70,
        "malware": 0.80, "cloud": 0.80, "iot": 0.80,
        "binary": 0.90, "binary_analysis": 0.90, "reverse_engineering": 0.90,
        "crypto": 0.90, "crypto_analysis": 0.90,
        "misc": 0.30, "unknown": 0.30,
    }
    return scores.get(domain.lower(), 0.30)


def _score_task_type(task_type: str) -> float:
    return _score_domain(task_type)  # same mapping covers task_type strings


def _score_tools(tools: List[str]) -> float:
    if not tools:
        return 0.20

    # Strip universal tools — they provide zero discriminatory signal
    # (FCA equivalence class #1: 16 tools with 100% co-occurrence across all 11 domains)
    signal_tools = [t for t in tools
                    if t.lower() not in _UNIVERSAL_TOOLS
                    and not any(t.lower().startswith(p) for p in _UNIVERSAL_PREFIXES)]

    if not signal_tools:
        return 0.15  # only universal tools → trivial task

    expert_count = sum(1 for t in signal_tools if t.lower() in _EXPERT_TOOLS)

    # Detect co-occurrence classes: if any member is found, infer the whole class
    cooccurrence_boost = 0.0
    detected_members = set()
    for cls in _COOCCURRENCE_CLASSES:
        found = {t.lower() for t in signal_tools} & {m.lower() for m in cls["members"]}
        if found:
            cooccurrence_boost = max(cooccurrence_boost, cls["complexity_boost"])
            detected_members.update(found)
        # Check original tools too (before universal filter)
        found_orig = {t.lower() for t in tools} & {m.lower() for m in cls["members"]}
        if found_orig:
            cooccurrence_boost = max(cooccurrence_boost, cls["complexity_boost"])

    # Single-domain tools are always expert-level
    domain_expert_count = sum(1 for t in signal_tools
                              if t.lower() in _SINGLE_DOMAIN_TOOLS)

    ratio = (expert_count + domain_expert_count * 0.8) / len(signal_tools)
    base = 0.20 + 0.75 * ratio
    return min(1.0, base + cooccurrence_boost)


def _score_estimated_minutes(minutes: int) -> float:
    if minutes <= 5:
        return 0.05
    if minutes <= 10:
        return 0.20
    if minutes <= 20:
        return 0.40
    if minutes <= 30:
        return 0.60
    if minutes <= 60:
        return 0.80
    return 0.95


def _score_critical_path(sg_id: str, critical_path: List[str]) -> float:
    return 1.0 if sg_id in critical_path else 0.0


def _score_dependencies(deps: List[str]) -> float:
    n = len(deps)
    if n == 0:
        return 0.00
    if n == 1:
        return 0.10
    if n == 2:
        return 0.30
    if n <= 4:
        return 0.50
    if n <= 6:
        return 0.70
    return 0.90


def _score_inputs(inputs: List[str]) -> float:
    n = len(inputs)
    if n <= 2:
        return 0.10
    if n <= 4:
        return 0.30
    if n <= 7:
        return 0.50
    return 0.80


def _score_dep_findings(dep_findings: Dict[str, list]) -> float:
    """Rich dependency findings = scaffolding = easier task.
    Returns a HIGH score for rich findings, but caller INVERTS it
    because scaffolding makes boost safer."""
    if not dep_findings:
        return 0.00
    total_findings = sum(len(v) for v in dep_findings.values())
    dep_count = len(dep_findings)
    if dep_count >= 2 and total_findings >= 4:
        return 0.95
    if dep_count >= 1 and total_findings >= 2:
        return 0.80
    return 0.60


# ═══════════════════════════════════════════════════════════════════
# KB Search
# ═══════════════════════════════════════════════════════════════════

def _find_kb_exact_match(sg: SubGoal, kb_root: str, threshold: int = 3) -> Optional[dict]:
    """Search KB for a solution matching this sub-goal."""
    try:
        from tools.kb.search import search_by_tags, search_by_tools
    except Exception:
        return None

    terms = [sg.domain, sg.task_type.replace("_analysis", "").replace("_", " ")]
    terms += sg.tools[:5]
    terms = list(set(t for t in terms if t))

    file_counts: Dict[str, int] = {}
    try:
        for term in terms:
            tag_hits = search_by_tags(term)
            for h in tag_hits:
                f = h if isinstance(h, str) else h.get("file", str(h))
                file_counts[f] = file_counts.get(f, 0) + 1
            tool_hits = search_by_tools(term)
            for h in tool_hits:
                f = h if isinstance(h, str) else h.get("file", str(h))
                file_counts[f] = file_counts.get(f, 0) + 1
    except Exception:
        return None

    if not file_counts:
        return None

    best_file = max(file_counts, key=lambda f: file_counts[f])
    best_count = file_counts[best_file]
    if best_count >= threshold:
        return {"file": best_file, "score": best_count}
    return None


# ═══════════════════════════════════════════════════════════════════
# Core Allocation
# ═══════════════════════════════════════════════════════════════════

def allocate_one(
    sg: SubGoal,
    plan,  # DecompositionPlan
    dep_findings: Optional[Dict[str, list]] = None,
    kb_root: str = "",
    config: Optional[AllocationConfig] = None,
) -> AllocationResult:
    """Score a single sub-goal and return its mode assignment."""
    cfg = config or AllocationConfig()
    dims: Dict[str, float] = {}

    dims["level"] = _score_level(sg.level)
    dims["domain"] = _score_domain(sg.domain)
    dims["task_type"] = _score_task_type(sg.task_type)
    dims["tools"] = _score_tools(sg.tools)
    dims["estimated_minutes"] = _score_estimated_minutes(sg.estimated_minutes)
    dims["critical_path"] = _score_critical_path(sg.id, getattr(plan, "critical_path", []))
    dims["dependencies"] = _score_dependencies(sg.dependencies)
    dims["inputs"] = _score_inputs(sg.inputs)

    dep_f = dep_findings or {}
    dep_findings_score = _score_dep_findings(dep_f)
    dims["dep_findings"] = dep_findings_score

    # Weighted score: dep_findings is INVERTED (rich findings = scaffolding = easier)
    weighted = (
        dims["level"] * cfg.weight_level +
        dims["domain"] * cfg.weight_domain +
        dims["task_type"] * cfg.weight_task_type +
        dims["tools"] * cfg.weight_tools +
        dims["estimated_minutes"] * cfg.weight_estimated_minutes +
        dims["critical_path"] * cfg.weight_critical_path +
        dims["dependencies"] * cfg.weight_dependencies +
        dims["inputs"] * cfg.weight_inputs +
        (1.0 - dims["dep_findings"]) * cfg.weight_dep_findings  # inverted
    )

    raw_score = weighted / cfg.total_weight
    raw_score = max(0.0, min(1.0, raw_score))

    # KB exact match check (can override)
    kb_match = None
    if cfg.kb_exact_match_overrides and kb_root:
        kb_match = _find_kb_exact_match(sg, kb_root, cfg.kb_match_threshold)

    if kb_match:
        mode = AllocationMode.BOOST
        reason = f"KB精确匹配: {kb_match['file']} (score={kb_match['score']})"
        kb_found = True
        kb_file = kb_match["file"]
    elif raw_score < cfg.boost_threshold:
        mode = AllocationMode.BOOST
        reason = f"复杂度={raw_score:.2f} < 阈值{cfg.boost_threshold} → BOOST"
        kb_found = False
        kb_file = ""
    else:
        mode = AllocationMode.FOCUSED
        reason = f"复杂度={raw_score:.2f} >= 阈值{cfg.boost_threshold} → FOCUSED"
        kb_found = False
        kb_file = ""

    # ── Logit capture ──────────────────────────────────────────
    try:
        from tools.logits import get_capture
        cap = get_capture()
        if cap.enabled:
            cap.record_alloc(
                sg_id=sg.id,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                complexity_score=raw_score,
                dimension_scores=dict(dims),
                mode=mode.value,
                reason=reason,
                kb_match_found=kb_found,
                kb_match_file=kb_file,
                weights={
                    "level": cfg.weight_level,
                    "domain": cfg.weight_domain,
                    "tools": cfg.weight_tools,
                    "estimated_minutes": cfg.weight_estimated_minutes,
                    "task_type": cfg.weight_task_type,
                    "critical_path": cfg.weight_critical_path,
                    "dependencies": cfg.weight_dependencies,
                    "inputs": cfg.weight_inputs,
                    "dep_findings": cfg.weight_dep_findings,
                },
                raw_weighted_sum=weighted,
            )
    except Exception:
        pass
    # ────────────────────────────────────────────────────────────

    return AllocationResult(
        sg_id=sg.id,
        mode=mode,
        complexity_score=raw_score,
        dimension_scores=dims,
        kb_match_found=kb_found,
        kb_match_file=kb_file,
        reason=reason,
    )


def allocate_all(
    plan,  # DecompositionPlan
    dep_findings: Optional[Dict[str, Dict[str, list]]] = None,
    kb_root: str = "",
    config: Optional[AllocationConfig] = None,
) -> AllocationPlan:
    """Batch-allocate all sub-goals in a plan."""
    result = AllocationPlan(challenge_name=plan.challenge_name)
    dep_f = dep_findings or {}

    boost_count = 0
    focused_count = 0

    for sg_id, sg in plan.sub_goals.items():
        # Collect dependency findings for this sub-goal
        sg_dep_findings = {
            dep_id: findings
            for dep_id in sg.dependencies
            if dep_id in dep_f and dep_f[dep_id]
        }
        allocation = allocate_one(sg, plan, sg_dep_findings, kb_root, config)
        result.allocations[sg_id] = allocation

        if allocation.mode == AllocationMode.BOOST:
            boost_count += 1
        else:
            focused_count += 1

    result.summary = {"boost": boost_count, "focused": focused_count}
    return result
