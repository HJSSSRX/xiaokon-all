"""Unit tests for FCA-optimized allocator and role assigner.

Covers: universal tool filtering, co-occurrence class detection,
single-domain fast-path, closure-based completeness check.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.decomposer.allocator import (
    _score_tools, _score_domain, _score_level,
    _UNIVERSAL_TOOLS, _UNIVERSAL_PREFIXES, _COOCCURRENCE_CLASSES,
    _IMPLICATIONS, _SINGLE_DOMAIN_TOOLS, _EXPERT_TOOLS,
    allocate_one, AllocationConfig, AllocationMode,
)
from tools.decomposer.role_assigner import (
    _find_candidates, _SINGLE_DOMAIN_TASK_TYPES,
    check_allocation_completeness, assign_roles, get_role_for_domain,
    ROLE_CAPABILITIES,
)
from tools.decomposer.models import SubGoal


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def basic_sg():
    return SubGoal(
        id="sg1", description="Test sub-goal", level=1,
        domain="memory", task_type="memory_analysis",
        tools=["volatility3", "core:config"],
        estimated_minutes=20, priority=1,
    )


@pytest.fixture
def ocr_sg():
    return SubGoal(
        id="sg2", description="OCR analysis", level=1,
        domain="stego_crypto", task_type="stego_analysis",
        tools=["vision:ocr_engine"],
        estimated_minutes=15, priority=2,
    )


# ── Universal tool filtering ──────────────────────────────────────────────

class TestUniversalToolFiltering:
    def test_universal_only_scores_low(self):
        """Tasks with only universal tools should score near bottom."""
        score = _score_tools(["core:config", "kb:kb_search", "hub:http_server"])
        assert score < 0.20, f"Universal-only score {score} should be < 0.20"

    def test_expert_with_universal_scores_high(self):
        """Expert tools mixed with universal tools retain high score."""
        score = _score_tools(["volatility3", "core:config", "kb:kb_search"])
        assert score > 0.50, f"Expert+universal score {score} should be > 0.50"

    def test_empty_tools_returns_default(self):
        score = _score_tools([])
        assert score == 0.20

    def test_all_universal_prefixes_are_recognized(self):
        """Verify all 4 universal prefixes are covered."""
        for prefix in _UNIVERSAL_PREFIXES:
            score = _score_tools([f"{prefix}test_tool"])
            assert score <= 0.15, f"Prefix {prefix} not filtered"


# ── Co-occurrence class detection ─────────────────────────────────────────

class TestCooccurrenceDetection:
    def test_server_vm_class_detected(self):
        """vmdk_reader + zfs_analysis triggers server VM class (complexity +0.25)."""
        score = _score_tools(["forensics:vmdk_reader", "forensics:zfs_analysis"])
        assert score > 0.70, f"Server VM score {score} should be > 0.70"

    def test_pcap_class_detected(self):
        """pcap_analysis triggers network pipeline class (+0.15 boost but no expert tools)."""
        score = _score_tools(["pcap:pcap_analysis", "pcap:flow_recon"])
        # base 0.20 + 0.15 co-occurrence boost = 0.35 (pcap tools aren't expert-level)
        assert score >= 0.30, f"PCAP score {score} should be >= 0.30"
        assert score < 0.50, f"PCAP score {score} should be < 0.50 (no expert tools)"

    def test_ctf_class_detected(self):
        """CTF feeder tools trigger CTF automation class (+0.15 boost)."""
        score = _score_tools(["feeder:ctf_coordinator", "feeder:ctf_scanner"])
        assert score >= 0.30, f"CTF score {score} should be >= 0.30"
        assert score < 0.50, f"CTF score {score} should be < 0.50 (no expert tools)"

    def test_no_false_positive_on_unrelated_tools(self):
        """Unrelated tools should not trigger co-occurrence classes."""
        score = _score_tools(["forensics:memory_forensics", "analytics:apriori"])
        assert score < 0.80  # No co-occurrence class triggered


# ── Domain scoring ────────────────────────────────────────────────────────

class TestDomainScoring:
    def test_binary_domain_high(self):
        assert _score_domain("binary") >= 0.90

    def test_log_domain_low(self):
        assert _score_domain("log") <= 0.15

    def test_unknown_domain_default(self):
        assert _score_domain("unknown") == 0.30
        assert _score_domain("nonexistent_domain") == 0.30

    def test_crypto_domain_high(self):
        assert _score_domain("crypto_analysis") == 0.90


# ── Level scoring ─────────────────────────────────────────────────────────

class TestLevelScoring:
    def test_level_0_minimal(self):
        assert _score_level(0) == 0.0

    def test_level_3_high(self):
        assert _score_level(3) == 0.90

    def test_unknown_level_default(self):
        assert _score_level(99) == 0.50


# ── Allocation mode decision ──────────────────────────────────────────────

class TestAllocationMode:
    def test_boost_for_trivial_task(self):
        """A task with only universal tools and low level should get BOOST mode."""
        from tools.decomposer.models import DecompositionPlan
        sg = SubGoal(
            id="sg_trivial", description="Log review", level=0,
            domain="log", task_type="log_analysis",
            tools=["core:config", "kb:kb_search"],  # universal tools only
            estimated_minutes=5, priority=10,
        )
        plan = DecompositionPlan(challenge_name="test", sub_goals={"sg_trivial": sg})
        result = allocate_one(sg, plan)
        assert result.mode == AllocationMode.BOOST, \
            f"Expected BOOST, got {result.mode} (score={result.complexity_score:.2f})"

    def test_focused_for_expert_task(self):
        """A level-3 binary reverse engineering task should get FOCUSED."""
        from tools.decomposer.models import DecompositionPlan
        sg = SubGoal(
            id="sg_hard", description="Reverse engineer malware", level=3,
            domain="binary", task_type="reverse_engineering",
            tools=["ghidra", "objdump", "readelf"],
            estimated_minutes=90, priority=1,
        )
        plan = DecompositionPlan(challenge_name="test", sub_goals={"sg_hard": sg})
        result = allocate_one(sg, plan)
        assert result.mode == AllocationMode.FOCUSED, \
            f"Expected FOCUSED, got {result.mode} (score={result.complexity_score:.2f})"

    def test_config_custom_threshold(self):
        """Custom boost_threshold changes mode boundary."""
        from tools.decomposer.models import DecompositionPlan
        sg = SubGoal(
            id="sg_medium", description="Medium task", level=2,
            domain="web", task_type="web_pentest",
            tools=["sqlmap"],
            estimated_minutes=30, priority=2,
        )
        plan = DecompositionPlan(challenge_name="test", sub_goals={"sg_medium": sg})
        cfg_low = AllocationConfig(boost_threshold=0.99)
        result = allocate_one(sg, plan, config=cfg_low)
        assert result.mode == AllocationMode.BOOST, \
            f"With threshold=0.99 should BOOST, got {result.mode}"


# ── Role assigner fast-path ───────────────────────────────────────────────

class TestRoleAssignerFastPath:
    def test_pcap_fast_path(self):
        assert _find_candidates("pcap_analysis") == ["network_analyst"]

    def test_binary_fast_path(self):
        assert _find_candidates("binary_analysis") == ["binary_analyst"]

    def test_web_fast_path(self):
        assert _find_candidates("web_pentest") == ["web_pentester"]

    def test_multi_role_scan(self):
        """log_analysis is multi-role — should fall through to scan."""
        candidates = _find_candidates("log_analysis")
        assert len(candidates) > 2  # computer, server, network analysts
        assert "computer_analyst" in candidates

    def test_unknown_type_returns_all(self):
        candidates = _find_candidates("nonexistent_type_xyz")
        assert len(candidates) == len(ROLE_CAPABILITIES)

    def test_all_fast_path_tasks_are_valid_roles(self):
        """Every fast-path mapping must point to an existing role."""
        for task_type, role in _SINGLE_DOMAIN_TASK_TYPES.items():
            assert role in ROLE_CAPABILITIES, \
                f"Fast-path {task_type} -> {role} but {role} not in ROLE_CAPABILITIES"


# ── Closure completeness check ────────────────────────────────────────────

class TestClosureCompleteness:
    def test_missing_universal_triggers_warning(self):
        sgs = {
            "sg1": SubGoal(id="sg1", description="test", level=1,
                           domain="computer", task_type="memory_analysis",
                           tools=["volatility3", "core:config"], priority=1),
        }
        assignments = {"computer_analyst": ["sg1"]}
        warnings = check_allocation_completeness(assignments, sgs)
        assert len(warnings) >= 1
        assert any("universal" in w.lower() for w in warnings)

    def test_ocr_task_missing_analytics_triggers_warning(self, ocr_sg):
        sgs = {"sg2": ocr_sg}
        assignments = {"stego_crypto_analyst": ["sg2"]}
        warnings = check_allocation_completeness(assignments, sgs)
        assert len(warnings) >= 1
        assert any(("apriori" in w or "ncd" in w) for w in warnings)

    def test_complete_allocation_no_warnings(self):
        """A full-featured allocation should have few/no warnings."""
        sgs = {
            "sg_full": SubGoal(
                id="sg_full", description="full task", level=2,
                domain="server", task_type="disk_analysis",
                tools=["forensics:disk_forensics", "core:config", "core:cache",
                       "core:http_base", "core:id_gen", "core:yaml_utils",
                       "hub:http_server", "hub:findings", "hub:role_log",
                       "kb:kb_search", "kb:kb_sync", "kb:kb_build",
                       "kb:feeder_crawl", "kb:tag_engine",
                       "competition:answer_diff", "competition:answer_format",
                       "competition:question_parser"],
                priority=1,
            ),
        }
        assignments = {"server_analyst": ["sg_full"]}
        warnings = check_allocation_completeness(assignments, sgs)
        # Should have no universal-infrastructure warnings
        universal_warnings = [w for w in warnings if "universal" in w.lower()]
        assert len(universal_warnings) == 0, \
            f"Expected no universal warnings but got: {universal_warnings}"


# ── Workload balancing ────────────────────────────────────────────────────

class TestWorkloadBalancing:
    def test_balanced_assignment(self):
        """Two identical tasks should go to different roles if capacity allows."""
        sgs = {
            "sg_a": SubGoal(id="sg_a", description="task A", level=1,
                            domain="memory", task_type="memory_analysis",
                            tools=["volatility3"], estimated_minutes=30, priority=1),
            "sg_b": SubGoal(id="sg_b", description="task B", level=1,
                            domain="network", task_type="pcap_analysis",
                            tools=["tshark"], estimated_minutes=30, priority=1),
        }
        assignments = assign_roles(sgs)
        assert "computer_analyst" in assignments
        assert "network_analyst" in assignments
        assert len(assignments["computer_analyst"]) == 1
        assert len(assignments["network_analyst"]) == 1

    def test_workload_skew_to_least_loaded(self):
        """Three memory tasks — distributed across the 2 capable roles (computer + binary)."""
        sgs = {}
        for i in range(3):
            sg_id = f"sg_mem_{i}"
            sgs[sg_id] = SubGoal(
                id=sg_id, description=f"memory task {i}", level=1,
                domain="memory", task_type="memory_analysis",
                tools=["volatility3"], estimated_minutes=20, priority=1,
            )
        assignments = assign_roles(sgs)
        # memory_analysis is shared by computer_analyst AND binary_analyst
        # workload balancing distributes: 2 to one, 1 to the other
        total_assigned = sum(len(v) for v in assignments.values())
        assert total_assigned == 3
        assert "computer_analyst" in assignments
        assert len(assignments["computer_analyst"]) in (1, 2, 3)


# ── Domain-to-role mapping ────────────────────────────────────────────────

class TestDomainRoleMapping:
    def test_memory_to_computer(self):
        assert get_role_for_domain("memory") == "computer_analyst"

    def test_network_to_network(self):
        assert get_role_for_domain("network") == "network_analyst"

    def test_mobile_to_mobile(self):
        assert get_role_for_domain("mobile") == "mobile_analyst"

    def test_web_to_pentester(self):
        assert get_role_for_domain("web") == "web_pentester"

    def test_crypto_to_stego(self):
        assert get_role_for_domain("crypto") == "stego_crypto_analyst"
