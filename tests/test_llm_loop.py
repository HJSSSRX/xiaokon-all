"""Tests for LLM agent loop orchestrator.

Covers: config defaults, decision parser, command sandbox, format lint,
round limit enforcement, session integration, BOOST delegation,
logit capture, EchoBackend e2e.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'D:/ai')

import pytest

# ── Test fixtures ────────────────────────────────────────────────────


def _make_minimal_plan():
    """Create a minimal 3-sub-goal DecompositionPlan for testing."""
    from tools.decomposer.models import DecompositionPlan, SubGoal, SubGoalLevel

    sg1 = SubGoal(
        id="SG-001", level=SubGoalLevel.SHARED,
        description="Index and hash all evidence files",
        domain="computer", task_type="index",
        inputs=["evidence.zip"], tools=["sha256sum", "file"],
        estimated_minutes=5, priority=1,
    )
    sg2 = SubGoal(
        id="SG-002", level=SubGoalLevel.ANALYSIS,
        description="Analyze memory dump for suspicious processes",
        domain="memory", task_type="memory_analysis",
        inputs=["memory.dmp"], outputs=["process_list.txt"],
        dependencies=["SG-001"], tools=["volatility3", "strings"],
        estimated_minutes=20, priority=2,
    )
    sg3 = SubGoal(
        id="SG-003", level=SubGoalLevel.QUESTION,
        description="Find the attacker's IP address",
        domain="network", task_type="question",
        dependencies=["SG-002"], tools=["tshark", "grep"],
        estimated_minutes=10, priority=1,
        question_text="What is the attacker's IP?",
        answer_format="ip",
    )

    plan = DecompositionPlan(
        challenge_name="test_challenge",
        challenge_description="A test challenge",
        sub_goals={"SG-001": sg1, "SG-002": sg2, "SG-003": sg3},
        topological_order=[["SG-001"], ["SG-002"], ["SG-003"]],
        critical_path=["SG-001", "SG-002", "SG-003"],
        critical_path_minutes=35,
    )
    return plan


def _make_session(tmpdir):
    """Create a minimal ExecutionSession with a temp case directory."""
    from tools.decomposer.session import ExecutionSession

    plan = _make_minimal_plan()
    case_dir = str(tmpdir)
    session = ExecutionSession.start(plan, case_dir)
    return session


class EchoBackend:
    """Mock LLM backend that returns pre-programmed responses."""
    name = "echo"

    def __init__(self, responses=None):
        self.model = "echo-test"
        self.responses = responses or []
        self.call_count = 0
        self.last_messages = None

    def chat(self, messages):
        self.last_messages = messages
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        # Default: return COMPLETE
        self.call_count += 1
        return "COMPLETE"


# ── Config Tests ──────────────────────────────────────────────────────


class TestConfig:
    def test_defaults(self):
        from tools.decomposer.llm_loop import LLMLoopConfig
        c = LLMLoopConfig()
        assert c.max_rounds_per_sg == 12
        assert c.max_total_rounds == 200
        assert c.tool_timeout == 120
        assert c.model_backend == "openai"
        assert c.model_temperature == 0.2
        assert c.delegate_boost is True
        assert c.command_sandbox is True
        assert c.format_lint is True

    def test_custom(self):
        from tools.decomposer.llm_loop import LLMLoopConfig
        c = LLMLoopConfig(
            model_backend="anthropic",
            model_name="claude-sonnet-4-6",
            max_rounds_per_sg=5,
            delegate_boost=False,
        )
        assert c.model_backend == "anthropic"
        assert c.model_name == "claude-sonnet-4-6"
        assert c.max_rounds_per_sg == 5
        assert c.delegate_boost is False


# ── Decision Parser Tests ─────────────────────────────────────────────


class TestDecisionParser:
    def setup_method(self):
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig
        # Create orchestrator with a mock session
        self.config = LLMLoopConfig()
        # We only test the parser, so no real session needed
        self.orch = LLMOrchestrator.__new__(LLMOrchestrator)
        self.ctx = {"sg_id": "SG-001", "answer_format": "flag{...}"}

    def test_parse_tool(self):
        result = self.orch._parse_llm_decision(
            "TOOL: volatility3 -f memory.dmp windows.pslist", self.ctx)
        assert result["type"] == "tool"
        assert "volatility3" in result["command"]

    def test_parse_tool_multiline(self):
        result = self.orch._parse_llm_decision(
            "分析后发现需要查看进程列表\n\nTOOL: volatility3 -f memory.dmp windows.pslist\n\n这将列出所有进程", self.ctx)
        assert result["type"] == "tool"
        assert "volatility3" in result["command"]

    def test_parse_kb_search(self):
        result = self.orch._parse_llm_decision(
            "KB_SEARCH: memory forensics process injection techniques", self.ctx)
        assert result["type"] == "kb_search"
        assert "memory" in result["query"]

    def test_parse_answer(self):
        result = self.orch._parse_llm_decision(
            "ANSWER: flag{test_found}\nCONFIDENCE: cross_source_high\nEVIDENCE_PATH: memory.dmp\nANALYSIS: Found in process list", self.ctx)
        assert result["type"] == "answer"
        assert result["answer"] == "flag{test_found}"
        assert result["confidence"] == "cross_source_high"
        assert result["evidence_path"] == "memory.dmp"

    def test_parse_answer_minimal(self):
        result = self.orch._parse_llm_decision("ANSWER: 192.168.1.100", self.ctx)
        assert result["type"] == "answer"
        assert result["answer"] == "192.168.1.100"
        assert result["confidence"] == "single_source_high"  # default

    def test_parse_complete(self):
        result = self.orch._parse_llm_decision("COMPLETE", self.ctx)
        assert result["type"] == "complete"

    def test_parse_complete_chinese(self):
        result = self.orch._parse_llm_decision("分析完成，标记完成", self.ctx)
        assert result["type"] == "complete"

    def test_parse_block(self):
        result = self.orch._parse_llm_decision("BLOCK: volatility3 not installed", self.ctx)
        assert result["type"] == "block"
        assert "volatility3" in result["reason"]

    def test_parse_block_chinese(self):
        result = self.orch._parse_llm_decision("阻塞: 缺少必要的取证工具", self.ctx)
        assert result["type"] == "block"

    def test_parse_unknown(self):
        result = self.orch._parse_llm_decision(
            "UNKNOWN\nREASON: after 3 rounds of analysis cannot determine the attacker IP", self.ctx)
        assert result["type"] == "unknown"
        assert "cannot determine" in result["reason"]

    def test_parse_unknown_no_reason(self):
        result = self.orch._parse_llm_decision("UNKNOWN", self.ctx)
        assert result["type"] == "unknown"
        assert result["reason"] == "模型无法判断"

    def test_parse_unknown_chinese(self):
        result = self.orch._parse_llm_decision("经过多次尝试，我无法判断这个问题的答案", self.ctx)
        assert result["type"] == "unknown"

    def test_parse_unknown_before_block(self):
        """UNKNOWN should be parsed before BLOCK even if '阻塞' appears in text."""
        result = self.orch._parse_llm_decision(
            "UNKNOWN\n无法判断，建议阻塞此子目标", self.ctx)
        assert result["type"] == "unknown"

    def test_parse_error(self):
        result = self.orch._parse_llm_decision("Just some random text without markers", self.ctx)
        assert result["type"] == "error"

    def test_parse_empty(self):
        result = self.orch._parse_llm_decision("", self.ctx)
        assert result["type"] == "error"

    def test_parse_tool_with_python(self):
        result = self.orch._parse_llm_decision(
            "TOOL: python3 tools/parse_dump.py memory.dmp", self.ctx)
        assert result["type"] == "tool"
        assert "python3" in result["command"]

    def test_parse_tool_priority_over_other_markers(self):
        """TOOL should be parsed first even if other markers exist."""
        result = self.orch._parse_llm_decision(
            "Let me try a tool first.\nTOOL: strings memory.dmp | grep ATTACKER\n"
            "If that works I'll submit ANSWER: something", self.ctx)
        assert result["type"] == "tool"


# ── Command Sandbox Tests ─────────────────────────────────────────────


class TestCommandSandbox:
    def test_allow_volatility(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("volatility3 -f evidence.dmp windows.pslist")
        assert ok
        assert err == ""

    def test_allow_strings(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("strings memory.dmp | grep -i flag")
        assert ok

    def test_allow_sqlite3(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("sqlite3 data.db '.tables'")
        assert ok

    def test_reject_rm_rf(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("rm -rf /")
        assert not ok
        assert "危险" in err

    def test_reject_dd(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("dd if=/dev/zero of=/dev/sda")
        assert not ok

    def test_reject_pip_install(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("pip install requests")
        assert not ok

    def test_reject_shutdown(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("shutdown -h now")
        assert not ok

    def test_reject_unknown_tool(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("unknown_tool --flag")
        assert not ok
        assert "白名单" in err

    def test_allow_python_tools_script(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("python3 tools/parse_dump.py memory.dmp")
        assert ok

    def test_reject_python_arbitrary(self):
        from tools.decomposer.llm_loop import _validate_command
        ok, err = _validate_command("python3 /etc/passwd")
        assert not ok


# ── Format Lint Tests ─────────────────────────────────────────────────


class TestFormatLint:
    def test_flag_format_ok(self):
        from tools.decomposer.llm_loop import _lint_answer
        assert _lint_answer("flag{th1s_1s_4_t3st}", "flag{...}") is True

    def test_flag_format_bad(self):
        from tools.decomposer.llm_loop import _lint_answer
        assert _lint_answer("not_a_flag", "flag{...}") is False

    def test_ip_format_ok(self):
        from tools.decomposer.llm_loop import _lint_answer
        assert _lint_answer("192.168.1.100", "ip") is True

    def test_ip_format_bad(self):
        from tools.decomposer.llm_loop import _lint_answer
        assert _lint_answer("not_an_ip", "ip") is False

    def test_md5_format_ok(self):
        from tools.decomposer.llm_loop import _lint_answer
        assert _lint_answer("d41d8cd98f00b204e9800998ecf8427e", "md5") is True

    def test_sha256_format_ok(self):
        from tools.decomposer.llm_loop import _lint_answer
        assert _lint_answer("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "sha256") is True

    def test_no_format_always_ok(self):
        from tools.decomposer.llm_loop import _lint_answer
        assert _lint_answer("anything_goes", "") is True


# ── Round Limit Tests ─────────────────────────────────────────────────


class TestRoundLimit:
    def test_max_rounds_auto_block(self, tmpdir):
        """Verify sub-goal is auto-blocked after max_rounds_per_sg."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=2, max_total_rounds=100)

        # Echo backend always returns unparseable text
        echo = EchoBackend(["gibberish not parseable"] * 10)

        orch = LLMOrchestrator(session, config)
        orch.backend = echo  # Inject mock

        # Run on first sub-goal
        ctx = session.next_ready_with_allocation()
        assert ctx.get("sg_id") == "SG-001"

        orch._run_one_sg(ctx)

        # After 2 unparseable rounds, SG-001 should be blocked
        assert session.state["SG-001"] == "blocked"
        assert "超过最大轮次" in session.blocked_reasons.get("SG-001", "")
        assert echo.call_count == 2


# ── Session Integration Tests ────────────────────────────────────────


class TestSessionIntegration:
    def test_complete_flow(self, tmpdir):
        """Test completing SG-001 via ANSWER action."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=5)

        echo = EchoBackend(["ANSWER: all files hashed\nCONFIDENCE: platform_confirmed"])
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        ctx = session.next_ready_with_allocation()
        orch._run_one_sg(ctx)

        assert session.state["SG-001"] == "completed"
        # SG-002 should be unblocked (its dep SG-001 is now complete)
        assert session.state["SG-002"] == "pending"

    def test_block_flow(self, tmpdir):
        """Test blocking a sub-goal via BLOCK action."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=5)

        echo = EchoBackend(["BLOCK: required tool not available"])
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        ctx = session.next_ready_with_allocation()
        orch._run_one_sg(ctx)

        assert session.state["SG-001"] == "blocked"

    def test_kb_then_answer_flow(self, tmpdir):
        """Test multi-round: KB search then answer."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=5)

        echo = EchoBackend([
            "KB_SEARCH: file hashing best practices",
            "ANSWER: all evidence indexed\nCONFIDENCE: platform_confirmed",
        ])
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        ctx = session.next_ready_with_allocation()
        orch._run_one_sg(ctx)

        assert session.state["SG-001"] == "completed"
        assert echo.call_count == 2
        assert len(orch.rounds) == 2
        assert orch.rounds[0].action_type == "kb_search"
        assert orch.rounds[1].action_type == "answer"

    def test_run_full_plan(self, tmpdir):
        """End-to-end: run all 3 sub-goals with EchoBackend."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=3, max_total_rounds=50)

        # Each sub-goal completes in 1 round
        echo = EchoBackend([
            "ANSWER: hashing done\nCONFIDENCE: platform_confirmed",
            "ANSWER: suspicious process found\nCONFIDENCE: cross_source_high",
            "ANSWER: 10.0.0.55\nCONFIDENCE: single_source_high",
        ])
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        result = orch.run()

        assert result["status"] == "complete"
        assert result["sub_goals_completed"] == 3
        assert result["total_rounds"] == 3
        assert session.is_complete()

    def test_unknown_block_flow(self, tmpdir):
        """Test that UNKNOWN action blocks the sub-goal with [UNKNOWN] prefix."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=5)

        echo = EchoBackend([
            "KB_SEARCH: test query",           # round 1: satisfy KB gate
            "UNKNOWN\nREASON: 证据不足无法判断",  # round 2: UNKNOWN accepted
        ])
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        ctx = session.next_ready_with_allocation()
        orch._run_one_sg(ctx)

        assert session.state["SG-001"] == "blocked"
        assert "[UNKNOWN]" in session.blocked_reasons.get("SG-001", "")
        # The last round should be unknown
        assert orch.rounds[-1].action_type == "unknown"

    def test_unknown_rejected_without_kb(self, tmpdir):
        """UNKNOWN is rejected if KB was never searched in this sub-goal."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=5)

        echo = EchoBackend([
            "UNKNOWN\nREASON: no idea",     # round 1: rejected, no KB search yet
            "KB_SEARCH: test query",       # round 2: KB searched
            "UNKNOWN\nREASON: still no idea",  # round 3: UNKNOWN accepted now
        ])
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        ctx = session.next_ready_with_allocation()
        orch._run_one_sg(ctx)

        # Should have run 3 rounds (reject → kb → accept)
        assert echo.call_count == 3
        assert orch.rounds[0].action_type == "unknown_rejected"
        assert orch.rounds[1].action_type == "kb_search"
        assert orch.rounds[2].action_type == "unknown"
        assert session.state["SG-001"] == "blocked"
        assert "[UNKNOWN]" in session.blocked_reasons.get("SG-001", "")

    def test_all_blocked_stops_loop(self, tmpdir):
        """Loop should stop when all remaining sub-goals are blocked."""
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=2)

        echo = EchoBackend(["BLOCK: no tools available"] * 10)
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        result = orch.run()

        assert result["status"] == "all_blocked"
        assert result["sub_goals_completed"] == 0


# ── Logit Capture Tests ──────────────────────────────────────────────


class TestLogitCapture:
    def test_llm_loop_logit_recorded(self, tmpdir):
        """Verify LLMLogit events are captured and serializable."""
        from tools.logits import get_capture
        from tools.decomposer.llm_loop import LLMOrchestrator, LLMLoopConfig

        cap = get_capture()
        cap.enable()
        cap.clear()

        session = _make_session(tmpdir)
        config = LLMLoopConfig(max_rounds_per_sg=3, capture_logits=True)

        echo = EchoBackend([
            "KB_SEARCH: test query",
            "TOOL: strings test.bin",
            "ANSWER: result\nCONFIDENCE: single_source_high",
        ])
        orch = LLMOrchestrator(session, config)
        orch.backend = echo

        ctx = session.next_ready_with_allocation()
        orch._run_one_sg(ctx)

        s = cap.summary()
        assert s["total_llm_rounds"] == 3
        assert s["llm_rounds_success"] == 3
        assert s["llm_actions"].get("kb_search") == 1
        assert s["llm_actions"].get("tool") == 1
        assert s["llm_actions"].get("answer") == 1

        # JSON serialization
        d = cap.to_dict()
        assert len(d["llm_loops"]) == 3
        assert d["llm_loops"][0]["type"] == "llm_loop"
        assert d["llm_loops"][0]["action_type"] == "kb_search"

        # JSONL (includes allocator events from JIT allocation)
        jsonl_path = os.path.join(str(tmpdir), "test_logits.jsonl")
        cap.write_jsonl(jsonl_path)
        with open(jsonl_path, encoding="utf-8") as f:
            lines = f.readlines()
        llm_lines = [l for l in lines if '"type": "llm_loop"' in l]
        assert len(llm_lines) == 3

        cap.clear()
        assert cap.summary()["total_llm_rounds"] == 0
        cap.disable()


# ── LLMRoundResult Tests ─────────────────────────────────────────────


class TestRoundResult:
    def test_dataclass_creation(self):
        from tools.decomposer.llm_loop import LLMRoundResult
        r = LLMRoundResult(
            sg_id="SG-001", round_num=1, action_type="tool",
            action_detail="volatility3 -f mem.dmp pslist",
            success=True, tool_output="PID 1234 suspicious",
        )
        assert r.sg_id == "SG-001"
        assert r.round_num == 1
        assert r.success is True
        assert "suspicious" in r.tool_output


# ── CLI Registration Test ────────────────────────────────────────────


class TestCLI:
    def test_llm_loop_help(self):
        """Verify llm-loop subcommand registers in CLI."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "tools.cli", "executor", "llm-loop", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        # Should show help, not an error
        assert "llm-loop" in result.stdout or "llm_loop" in result.stdout or result.returncode == 0


# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
