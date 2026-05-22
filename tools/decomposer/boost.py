"""Weak Model Boost Orchestrator — makes weak AI perform beyond its baseline.

Core loop for each sub-goal:
  1. KB search → exact match? → copy-paste commands (skip model inference)
  2. No KB match → compact fill-in-the-blank prompt → model inference
  3. Multi-layer validation: command sandbox → format lint → confidence check
  4. Fail → retry (different temperature) → multi-sample voting → escalate
  5. Pass → record, unblock next

Integrates with:
  - tools/local_agent.py backends (5 inference engines)
  - tools/kb/search.py (consultant search)
  - tools/answer_format_lint.py (format validation)
  - tools/core/tool_pool.py (tool execution sandbox)
  - tools/decomposer/session.py (state tracking)
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from tools.decomposer.models import SubGoal, SubGoalLevel


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Boost Configuration ──────────────────────────────────────────

@dataclass
class BoostConfig:
    """Configuration for the boost orchestrator."""
    kb_first: bool = True              # Always search KB before model inference
    kb_match_threshold: int = 3         # Score threshold for "KB has answer"
    max_retries: int = 2                # Max retries before voting
    voting_samples: int = 3             # Samples for multi-sample voting
    voting_threshold: float = 0.5       # Fraction of samples that must agree
    temperature_high: float = 0.3       # Temperature for first attempt
    temperature_retry: float = 0.7      # Temperature for retry (more creative)
    temperature_voting: float = 0.8     # Temperature for voting samples
    confidence_floor: str = "single_source_high"  # Minimum acceptable confidence
    escalate_on_all_fail: bool = True   # Escalate when all attempts fail
    command_sandbox: bool = True        # Validate commands against allowlist
    format_lint: bool = True            # Validate answer formats
    log_every_step: bool = True         # Verbose logging


# Confidence hierarchy (lower index = higher confidence)
CONFIDENCE_LEVELS = [
    "platform_confirmed",
    "self_verified_db",
    "cross_source_high",
    "single_source_high",
    "gui_observed",
    "placeholder",
]

# Command allowlist (from local_agent.py)
_ALLOWED_TOOLS = {
    "volatility3", "vol", "strings", "grep", "file", "stat", "sha256sum", "md5sum",
    "tshark", "wireshark", "ngrep", "tcpdump", "nmap", "sqlmap", "sqlite3",
    "binwalk", "steghide", "exiftool", "strings2", "foremost", "bulk_extractor",
    "fls", "fsstat", "icat", "ewfmount", "mount", "losetup", "qemu-img",
    "adb", "apktool", "jadx", "unzip", "unrar", "7z", "tar", "gpg", "openssl",
    "objdump", "readelf", "ida", "ghidra", "objcopy", "curl", "wget", "jq",
    "python", "python3", "pip", "git", "docker", "xxd", "base64", "cut", "sort",
    "uniq", "head", "tail", "wc", "find", "locate",
}

_DANGEROUS_PATTERNS = [
    r'rm\s+-rf', r'format\s+[A-Z]:', r'dd\s+if=', r'shutdown', r'reboot',
    r'>\s*/dev/', r'mkfs', r'fdisk', r'chmod\s+777', r'eval\s+',
    r'pip\s+install', r'npm\s+install\s+-g', r'curl.*\|.*sh',
]


# ── Boost Result ──────────────────────────────────────────────────

@dataclass
class BoostResult:
    """Result of a single sub-goal boost attempt."""
    sg_id: str
    success: bool
    method: str = ""                  # "kb_copy", "model_inference", "voting", "escalated"
    commands: List[str] = field(default_factory=list)
    findings: List[dict] = field(default_factory=list)
    answer: str = ""
    confidence: str = "placeholder"
    validation_errors: List[str] = field(default_factory=list)
    attempts: int = 0
    raw_outputs: List[str] = field(default_factory=list)
    kb_hits: List[dict] = field(default_factory=list)
    error: str = ""
    timestamp: str = ""


# ── Boost Orchestrator ────────────────────────────────────────────

class BoostOrchestrator:
    """Orchestrates the weak model amplification pipeline for one sub-goal."""

    def __init__(self, config: Optional[BoostConfig] = None, kb_root: str = ""):
        self.config = config or BoostConfig()
        self.kb_root = kb_root or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "knowledge"
        )

    def execute(self, context: dict, case_dir: str = ".") -> BoostResult:
        """Run the full boost pipeline for a sub-goal.

        Args:
            context: The context dict from session.focus().
            case_dir: Working directory.

        Returns:
            BoostResult with findings, answer, and confidence.
        """
        sg_id = context.get("sg_id", "?")
        result = BoostResult(sg_id=sg_id, success=False, timestamp=_now())

        # ── Step 1: KB-first search ─────────────────────────────
        if self.config.kb_first:
            kb_hits = self._kb_search(context)
            result.kb_hits = kb_hits

            exact_match = self._find_exact_match(kb_hits, context)
            if exact_match:
                result.method = "kb_copy"
                result.commands = exact_match.get("commands", [])
                result.answer = exact_match.get("answer", "")
                result.confidence = "cross_source_high"
                result.success = True
                self._log(f"[{sg_id}] KB精确匹配! 跳过模型推理, 直接复制命令")
                return result

        # ── Step 2: Compact prompt → model inference ────────────
        prompt = self._build_compact_prompt(context, result.kb_hits)
        result.attempts = 1

        output = self._call_model(prompt, temperature=self.config.temperature_high)
        result.raw_outputs.append(output or "")

        parsed = self._parse_response(output or "")
        result.commands = parsed.get("commands", [])
        result.answer = parsed.get("answer", "")
        result.confidence = parsed.get("confidence", "single_source_high")

        # ── Step 3: Multi-layer validation ──────────────────────
        errors = self._validate(result, context)
        result.validation_errors = errors

        if not errors:
            result.method = "model_inference"
            result.success = True
            self._log(f"[{sg_id}] 模型推理通过 (confidence={result.confidence})")
            return result

        self._log(f"[{sg_id}] 验证失败: {errors}")

        # ── Step 4: Retry with different temperature ────────────
        for retry in range(self.config.max_retries):
            self._log(f"[{sg_id}] 重试 {retry + 1}/{self.config.max_retries} (temp={self.config.temperature_retry})")
            result.attempts += 1

            output = self._call_model(prompt, temperature=self.config.temperature_retry)
            result.raw_outputs.append(output or "")

            parsed = self._parse_response(output or "")
            result.commands = parsed.get("commands", [])
            result.answer = parsed.get("answer", "")
            result.confidence = parsed.get("confidence", "single_source_high")

            errors = self._validate(result, context)
            result.validation_errors = errors

            if not errors:
                result.method = "model_inference"
                result.success = True
                self._log(f"[{sg_id}] 重试{retry + 1}通过")
                return result

        # ── Step 5: Multi-sample voting ─────────────────────────
        if self.config.voting_samples >= 3:
            self._log(f"[{sg_id}] 进入多路投票模式 ({self.config.voting_samples}路采样)")
            vote_result = self._multi_sample_vote(prompt, context)
            if vote_result.success:
                result.method = "voting"
                result.commands = vote_result.commands
                result.answer = vote_result.answer
                result.confidence = vote_result.confidence
                result.success = True
                result.attempts += self.config.voting_samples
                result.raw_outputs.extend(vote_result.raw_outputs)
                return result

        # ── Step 6: Escalate ────────────────────────────────────
        if self.config.escalate_on_all_fail:
            result.method = "escalated"
            result.error = f"所有尝试失败 ({result.attempts}次推理 + 投票), 已标记为需升级"
            self._log(f"[{sg_id}] 升级: {result.error}")

        return result

    # ── Internal: KB Search ──────────────────────────────────────

    def _kb_search(self, context: dict) -> List[dict]:
        """Search KB for prior solutions matching this sub-goal."""
        terms = context.get("kb_search_terms", [])
        domain = context.get("domain", "")
        task_type = context.get("task_type", "")

        query_terms = list(set(terms + [domain, task_type.replace("_analysis", "")]))
        query_terms = [t for t in query_terms if t]

        hits = []
        try:
            from tools.kb.search import search_by_tags, search_by_tools
            for term in query_terms[:5]:
                tag_hits = search_by_tags(term)
                if tag_hits:
                    for h in tag_hits:
                        hits.append({"source": "tag", "term": term, "file": h})
                tool_hits = search_by_tools(term)
                if tool_hits:
                    for h in tool_hits:
                        hits.append({"source": "tool", "term": term, "file": h})
        except Exception:
            pass

        return hits

    def _find_exact_match(self, kb_hits: List[dict], context: dict) -> Optional[dict]:
        """Determine if KB hits are good enough to skip model inference entirely."""
        if not kb_hits:
            return None

        # Count hits per file — if a file appears 3+ times across different terms, it's a strong match
        file_counts: Dict[str, int] = {}
        for h in kb_hits:
            f = h.get("file", "")
            file_counts[f] = file_counts.get(f, 0) + 1

        best_file = max(file_counts, key=lambda f: file_counts[f]) if file_counts else ""
        best_count = file_counts.get(best_file, 0)

        if best_count >= self.config.kb_match_threshold and best_file:
            # Read the solution file and extract commands + answer
            commands, answer = self._extract_from_solution(best_file)
            if commands:
                return {"file": best_file, "commands": commands, "answer": answer, "score": best_count}

        return None

    def _extract_from_solution(self, filepath: str) -> Tuple[List[str], str]:
        """Extract CLI commands and answer from a knowledge/solved/ file."""
        commands = []
        answer = ""
        try:
            kb_dir = self.kb_root
            full_path = os.path.join(kb_dir, "solved", filepath) if not os.path.isabs(filepath) else filepath
            if not os.path.exists(full_path):
                # Try skills/
                full_path = os.path.join(kb_dir, "skills", filepath)

            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Extract code blocks (commands)
                for m in re.finditer(r'```(?:bash|shell|sh|powershell)?\n(.*?)```', content, re.DOTALL):
                    for line in m.group(1).strip().split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("//"):
                            commands.append(line)

                # Extract answer
                ans_m = re.search(r'(?:##\s*Answer|答案|flag|Flag)[:\s]*([^\n]+)', content)
                if ans_m:
                    answer = ans_m.group(1).strip()
        except Exception:
            pass
        return commands, answer

    # ── Internal: Prompt Building ────────────────────────────────

    def _build_compact_prompt(self, context: dict, kb_hits: List[dict]) -> str:
        """Build a compact, fill-in-the-blank prompt for the weak model."""
        sg_id = context.get("sg_id", "?")
        description = context.get("description", "")
        domain = context.get("domain", "")
        task_type = context.get("task_type", "")
        tools = context.get("tools", [])
        inputs = context.get("inputs", [])
        answer_format = context.get("answer_format", "")
        question_text = context.get("question_text", "")
        dep_findings = context.get("dep_findings", {})
        level_name = context.get("level_name", "")

        # KB context summary
        kb_context = "无匹配的先例方案"
        if kb_hits:
            kb_files = list(set(h.get("file", "") for h in kb_hits[:5]))
            kb_context = "相关方案: " + ", ".join(kb_files[:3])

        # Dependency findings summary
        dep_summary = ""
        if dep_findings:
            for dep_id, findings in dep_findings.items():
                for f in findings[:2]:
                    dep_summary += f"- {dep_id}: {f.get('finding', f.get('tool', ''))[:100]}\n"

        lines = [
            f"# 你是 {domain or 'forensic'} 分析师 — 低算力聚焦模式",
            f"",
            f"## 任务 ({level_name})",
            f"{description}",
            f"",
            f"## 可用工具",
            f"{', '.join(tools[:5]) if tools else 'file, strings, grep'}",
            f"",
            f"## 检材文件",
            f"{', '.join(inputs[:5]) if inputs else '(由前置步骤准备)'}",
            f"",
        ]

        if dep_summary:
            lines.append("## 前置发现 (已完成依赖子目标的输出)")
            lines.append(dep_summary)
            lines.append("")

        if kb_context != "无匹配的先例方案":
            lines.append(f"## 知识库参考")
            lines.append(f"{kb_context}")
            lines.append("")

        if question_text:
            lines.append(f"## 题目")
            lines.append(f"{question_text}")
            if answer_format:
                lines.append(f"答案格式: {answer_format}")
            lines.append("")

        lines.append("## 操作指令 (只输出以下4种格式之一)")
        lines.append("")
        lines.append("如果需要执行命令:")
        lines.append("```")
        lines.append("TOOL: volatility3 -f evidence.dmp windows.pslist")
        lines.append("```")
        lines.append("")
        lines.append("如果需要搜索知识库:")
        lines.append("```")
        lines.append("KB_SEARCH: memory forensics process injection")
        lines.append("```")
        lines.append("")
        lines.append("如果已得出答案:")
        lines.append("```")
        lines.append("ANSWER: flag{found_answer}")
        lines.append("confidence: self_verified_db")
        lines.append("evidence_path: /path/to/evidence")
        lines.append("analysis: 推导步骤...")
        lines.append("```")
        lines.append("")
        lines.append("如果需要求助:")
        lines.append("```")
        lines.append("LOG_NEED: 需要跨角色协助的具体内容")
        lines.append("```")
        lines.append("")
        lines.append("**现在直接开始。不要提问。不要解释。只输出上述4种格式之一。**")

        return "\n".join(lines)

    # ── Internal: Model Inference ─────────────────────────────────

    def _call_model(self, prompt: str, temperature: float = 0.3) -> Optional[str]:
        """Call the configured model backend. Tries local_agent backends."""
        try:
            from tools.local_agent import _create_backend

            # Try to load agent config
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "config", "agent.yaml"
            )
            backend = _create_backend(config_path if os.path.exists(config_path) else None)

            messages = [{"role": "user", "content": prompt}]
            output = backend.chat(messages, temperature=temperature, max_tokens=1024)
            return output
        except Exception as e:
            self._log(f"模型调用失败: {e}")
            return None

    # ── Internal: Response Parsing ────────────────────────────────

    def _parse_response(self, text: str) -> dict:
        """Parse weak model output into structured actions."""
        if not text:
            return {"commands": [], "answer": "", "confidence": "placeholder"}

        result = {"commands": [], "answer": "", "confidence": "single_source_high"}

        # TOOL: command
        for m in re.finditer(r'TOOL:\s*(.+?)(?:\n|$)', text, re.IGNORECASE):
            cmd = m.group(1).strip()
            if cmd:
                result["commands"].append(cmd)

        # ANSWER: answer text
        ans_m = re.search(r'ANSWER:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if ans_m:
            result["answer"] = ans_m.group(1).strip()

        # confidence: level
        conf_m = re.search(r'confidence:\s*(\w+)', text, re.IGNORECASE)
        if conf_m:
            conf_val = conf_m.group(1).strip().lower()
            if conf_val in CONFIDENCE_LEVELS:
                result["confidence"] = conf_val

        # Also extract code blocks as commands
        for m in re.finditer(r'```(?:bash|shell|sh)?\n(.+?)```', text, re.DOTALL):
            for line in m.group(1).strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("//"):
                    if line not in result["commands"]:
                        result["commands"].append(line)

        return result

    # ── Internal: Validation ──────────────────────────────────────

    def _validate(self, result: BoostResult, context: dict) -> List[str]:
        """Multi-layer validation. Returns list of error messages (empty = pass)."""
        errors = []

        # Layer 1: Command sandbox
        if self.config.command_sandbox:
            for cmd in result.commands:
                tool_name = cmd.split()[0] if cmd.split() else ""
                if tool_name and tool_name not in _ALLOWED_TOOLS:
                    errors.append(f"工具不在白名单: {tool_name}")
                for pattern in _DANGEROUS_PATTERNS:
                    if re.search(pattern, cmd):
                        errors.append(f"危险命令模式: {pattern}")

        # Layer 2: Format lint (for question-level sub-goals)
        if self.config.format_lint and context.get("level") == SubGoalLevel.QUESTION:
            answer_format = context.get("answer_format", "")
            answer = result.answer
            if answer_format and answer:
                format_ok = self._lint_answer_format(answer, answer_format)
                if not format_ok:
                    errors.append(f"答案格式不匹配预期: {answer_format}")

        # Layer 3: Confidence floor
        conf_idx = CONFIDENCE_LEVELS.index(result.confidence) if result.confidence in CONFIDENCE_LEVELS else 99
        floor_idx = CONFIDENCE_LEVELS.index(self.config.confidence_floor)
        if conf_idx > floor_idx and context.get("level") == SubGoalLevel.QUESTION:
            errors.append(f"置信度不足: {result.confidence} < {self.config.confidence_floor}")

        # Layer 4: Must have at least one command OR answer
        if not result.commands and not result.answer:
            errors.append("模型未输出任何命令或答案")

        return errors

    def _lint_answer_format(self, answer: str, expected_format: str) -> bool:
        """Check if answer matches expected format."""
        format_rules = {
            "flag{...}": r'flag\{.+\}',
            "IP地址": r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
            "MD5/SHA": r'[0-9a-fA-F]{32,64}',
            "时间戳/日期": r'\d{4}[-/]\d{2}[-/]\d{2}',
            "手机号/号码": r'\d{7,15}',
            "文件路径": r'[/\\]',
            "文本/密码": r'.{1,100}',
        }
        for rule_name, pattern in format_rules.items():
            if rule_name in expected_format or expected_format in rule_name:
                return bool(re.search(pattern, answer))
        return True  # If no specific rule matches, accept

    # ── Internal: Multi-sample Voting ─────────────────────────────

    def _multi_sample_vote(self, prompt: str, context: dict) -> BoostResult:
        """Run multiple inference samples and majority-vote the answer."""
        samples = []
        answers = []
        all_commands = []

        for i in range(self.config.voting_samples):
            output = self._call_model(prompt, temperature=self.config.temperature_voting)
            if output:
                samples.append(output)
                parsed = self._parse_response(output)
                if parsed["answer"]:
                    answers.append(parsed["answer"])
                all_commands.extend(parsed.get("commands", []))

        result = BoostResult(sg_id=context.get("sg_id", "?"), success=False)
        result.raw_outputs = samples
        result.attempts = self.config.voting_samples

        if not answers and not all_commands:
            return result

        # Majority vote on answer
        if answers:
            from collections import Counter
            answer_counts = Counter(answers)
            most_common = answer_counts.most_common(1)[0]
            vote_ratio = most_common[1] / len(answers)

            if vote_ratio >= self.config.voting_threshold:
                result.answer = most_common[0]
                result.confidence = "cross_source_high" if vote_ratio >= 0.8 else "single_source_high"
                result.success = True
                self._log(f"投票通过: {most_common[1]}/{len(answers)} ({vote_ratio:.0%}) = {most_common[0][:60]}")

        # Deduplicate commands
        seen = set()
        result.commands = []
        for cmd in all_commands:
            if cmd not in seen:
                seen.add(cmd)
                result.commands.append(cmd)

        return result

    # ── Helpers ────────────────────────────────────────────────────

    def _log(self, msg: str):
        if self.config.log_every_step:
            print(f"[boost] {msg}", file=sys.stderr)


# ── Convenience Functions ─────────────────────────────────────────

def boost_subgoal(context: dict, case_dir: str = ".", config: Optional[BoostConfig] = None) -> BoostResult:
    """Run boost on a single sub-goal. One-shot convenience function."""
    orch = BoostOrchestrator(config=config)
    return orch.execute(context, case_dir)


def quick_boost(sg_description: str, domain: str = "", tools: List[str] = None) -> BoostResult:
    """Quick boost from minimal context — no session needed."""
    context = {
        "sg_id": "quick",
        "description": sg_description,
        "domain": domain,
        "task_type": f"{domain}_analysis" if domain else "",
        "tools": tools or ["file", "strings", "grep"],
        "inputs": [],
        "dep_findings": {},
        "kb_search_terms": [domain] if domain else [],
        "level": SubGoalLevel.ANALYSIS,
        "level_name": "领域分析",
        "answer_format": "",
        "question_text": sg_description,
    }
    return boost_subgoal(context)
