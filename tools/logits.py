"""Orchestrator tool-call logit capture.

Hooks into the allocator (9-dimension scores) and boost pipeline
(model outputs, voting probabilities, confidence, validation) to
persist structured decision traces for later analysis.

Usage:
    from tools.logits import LogitCapture, get_capture

    cap = get_capture()                # singleton
    cap.enable()                       # start recording
    # … run decompose + allocate + boost …
    cap.write_jsonl("trace.jsonl")     # persist
    cap.clear()                        # reset
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Trace event types ───────────────────────────────────────────────

@dataclass
class AllocatorLogit:
    """Single allocation scoring trace."""
    sg_id: str
    timestamp: str = ""
    complexity_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    mode: str = ""                     # "boost" | "focused"
    reason: str = ""
    kb_match_found: bool = False
    kb_match_file: str = ""
    weights: Dict[str, float] = field(default_factory=dict)
    raw_weighted_sum: float = 0.0

    def to_dict(self) -> dict:
        return {
            "type": "allocator",
            "sg_id": self.sg_id,
            "timestamp": self.timestamp,
            "complexity_score": round(self.complexity_score, 4),
            "dimension_scores": {k: round(v, 4) for k, v in self.dimension_scores.items()},
            "mode": self.mode,
            "reason": self.reason,
            "kb_match_found": self.kb_match_found,
            "kb_match_file": self.kb_match_file,
            "weights": {k: round(v, 2) for k, v in self.weights.items()},
            "raw_weighted_sum": round(self.raw_weighted_sum, 4),
        }


@dataclass
class BoostLogit:
    """Single boost pipeline trace."""
    sg_id: str
    timestamp: str = ""
    success: bool = False
    method: str = ""                   # "kb_copy" | "model_inference" | "voting" | "escalated"
    confidence: str = "placeholder"
    attempts: int = 0
    temperature: float = 0.0
    validation_errors: List[str] = field(default_factory=list)
    answer: str = ""
    kb_hit_count: int = 0
    voting_ratio: Optional[float] = None
    raw_outputs_snippets: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": "boost",
            "sg_id": self.sg_id,
            "timestamp": self.timestamp,
            "success": self.success,
            "method": self.method,
            "confidence": self.confidence,
            "attempts": self.attempts,
            "temperature": self.temperature,
            "validation_errors": self.validation_errors,
            "answer": self.answer[:200] if self.answer else "",
            "kb_hit_count": self.kb_hit_count,
            "voting_ratio": round(self.voting_ratio, 4) if self.voting_ratio is not None else None,
            "raw_outputs_snippets": [s[:120] for s in self.raw_outputs_snippets],
        }


@dataclass
class ModelCallLogit:
    """Low-level model call trace — raw prompt, output, timing."""
    sg_id: str
    timestamp: str = ""
    model_backend: str = ""
    temperature: float = 0.0
    prompt_chars: int = 0
    output_chars: int = 0
    latency_ms: float = 0.0
    tokens_est: int = 0
    prompt_snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "model_call",
            "sg_id": self.sg_id,
            "timestamp": self.timestamp,
            "model_backend": self.model_backend,
            "temperature": self.temperature,
            "prompt_chars": self.prompt_chars,
            "output_chars": self.output_chars,
            "latency_ms": self.latency_ms,
            "tokens_est": self.tokens_est,
            "prompt_snippet": self.prompt_snippet[:120],
        }


# ── Capture singleton ───────────────────────────────────────────────

class LogitCapture:
    """Thread-safe singleton that collects tool-call logits from the
    allocator and boost pipeline."""

    def __init__(self):
        self._enabled: bool = False
        self._lock = threading.Lock()
        self.allocations: List[AllocatorLogit] = []
        self.boosts: List[BoostLogit] = []
        self.model_calls: List[ModelCallLogit] = []
        self.llm_loops: List[Dict] = []

    # ── lifecycle ─────────────────────────────────────────────────

    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def clear(self) -> None:
        with self._lock:
            self.allocations.clear()
            self.boosts.clear()
            self.model_calls.clear()
            self.llm_loops.clear()

    # ── record ────────────────────────────────────────────────────

    def record_alloc(self, **kwargs) -> None:
        if not self._enabled:
            return
        entry = AllocatorLogit(**kwargs)
        with self._lock:
            self.allocations.append(entry)

    def record_boost(self, **kwargs) -> None:
        if not self._enabled:
            return
        entry = BoostLogit(**kwargs)
        with self._lock:
            self.boosts.append(entry)

    def record_model_call(self, **kwargs) -> None:
        if not self._enabled:
            return
        entry = ModelCallLogit(**kwargs)
        with self._lock:
            self.model_calls.append(entry)

    def record_llm_loop(self, **kwargs) -> None:
        if not self._enabled:
            return
        entry = {
            "type": "llm_loop",
            "sg_id": kwargs.get("sg_id", ""),
            "round_num": kwargs.get("round_num", 0),
            "timestamp": kwargs.get("timestamp", ""),
            "action_type": kwargs.get("action_type", ""),
            "action_detail": kwargs.get("action_detail", "")[:200],
            "success": kwargs.get("success", False),
            "tool_output_snippet": kwargs.get("tool_output_snippet", "")[:200],
            "kb_hits": kwargs.get("kb_hits", 0),
            "llm_decision_snippet": kwargs.get("llm_decision_snippet", "")[:200],
            "error": kwargs.get("error", ""),
        }
        with self._lock:
            self.llm_loops.append(entry)

    # ── aggregate ─────────────────────────────────────────────────

    def summary(self) -> dict:
        with self._lock:
            allocs = list(self.allocations)
            boosts = list(self.boosts)
            calls = list(self.model_calls)
            loops = list(self.llm_loops)
        return self._compute_summary(allocs, boosts, calls, loops)

    # ── serialization ─────────────────────────────────────────────

    def _compute_summary(self, allocs, boosts, calls, loops=None) -> dict:
        """Compute summary from already-snapshotted lists (no lock)."""
        if loops is None:
            loops = []
        boost_ok = sum(1 for b in boosts if b.success)
        methods = {}
        for b in boosts:
            methods[b.method] = methods.get(b.method, 0) + 1
        confs = {}
        for b in boosts:
            confs[b.confidence] = confs.get(b.confidence, 0) + 1
        modes = {}
        for a in allocs:
            modes[a.mode] = modes.get(a.mode, 0) + 1
        llm_actions = {}
        llm_ok = 0
        for r in loops:
            at = r.get("action_type", "")
            llm_actions[at] = llm_actions.get(at, 0) + 1
            if r.get("success"):
                llm_ok += 1
        return {
            "total_allocations": len(allocs),
            "total_boosts": len(boosts),
            "total_model_calls": len(calls),
            "total_llm_rounds": len(loops),
            "llm_rounds_success": llm_ok,
            "llm_actions": llm_actions,
            "boost_success_rate": boost_ok / len(boosts) if boosts else 0,
            "methods": methods,
            "confidences": confs,
            "modes": modes,
            "avg_complexity": (
                sum(a.complexity_score for a in allocs) / len(allocs) if allocs else 0
            ),
            "total_latency_ms": sum(c.latency_ms for c in calls),
        }

    def to_dict(self) -> dict:
        with self._lock:
            allocs = list(self.allocations)
            boosts = list(self.boosts)
            calls = list(self.model_calls)
            loops = list(self.llm_loops)
        return {
            "meta": {
                "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "summary": self._compute_summary(allocs, boosts, calls, loops),
            },
            "allocations": [a.to_dict() for a in allocs],
            "boosts": [b.to_dict() for b in boosts],
            "model_calls": [m.to_dict() for m in calls],
            "llm_loops": loops,
        }

    def write_json(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def write_jsonl(self, path: str) -> None:
        """Write one JSON object per line — good for streaming / tail -f."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with self._lock:
            allocs = list(self.allocations)
            boosts = list(self.boosts)
            calls = list(self.model_calls)
            loops = list(self.llm_loops)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for a in allocs:
                f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")
            for b in boosts:
                f.write(json.dumps(b.to_dict(), ensure_ascii=False) + "\n")
            for m in calls:
                f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")
            for r in loops:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def write_compact_scores(self, path: str) -> None:
        """Write a minimal TSV: sg_id | complexity | mode | 9 dims."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with self._lock:
            allocs = list(self.allocations)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            header = ["sg_id", "complexity", "mode"]
            if allocs:
                sample = allocs[0].dimension_scores
                header += list(sample.keys())
            f.write("\t".join(header) + "\n")
            for a in allocs:
                row = [a.sg_id, str(round(a.complexity_score, 4)), a.mode]
                for dim in header[3:]:
                    row.append(str(round(a.dimension_scores.get(dim, 0), 4)))
                f.write("\t".join(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)


# ── Global singleton ────────────────────────────────────────────────

_capture: Optional[LogitCapture] = None


def get_capture() -> LogitCapture:
    global _capture
    if _capture is None:
        _capture = LogitCapture()
    return _capture
