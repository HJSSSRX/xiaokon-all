"""Execution session state machine for focused sub-goal execution.

Tracks progress through a DecompositionPlan: which sub-goal is current,
which are completed/blocked/pending, what findings have been produced.

The session is the Python half of the focused execution system.
The AI half is in prompts/protocols/focused_execution.md.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from tools.decomposer.models import DecompositionPlan, SubGoal, SubGoalLevel


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ExecutionSession:
    """Tracks execution progress through a DecompositionPlan.

    State machine: pending -> in_focus -> completed (or blocked).
    Dependents of a completed sub-goal are automatically unblocked.
    """

    plan: DecompositionPlan
    state: Dict[str, str] = field(default_factory=dict)
    findings: Dict[str, list] = field(default_factory=dict)
    current_sg_id: Optional[str] = None
    started_at: str = ""
    completed_at: Optional[str] = None
    case_dir: str = ""
    blocked_reasons: Dict[str, str] = field(default_factory=dict)
    boost_mode: bool = False
    boost_results: Dict[str, dict] = field(default_factory=dict)
    allocations: Dict[str, dict] = field(default_factory=dict)
    allocation_overrides: Dict[str, str] = field(default_factory=dict)

    # ── Factory Methods ──────────────────────────────────────────

    @classmethod
    def start(cls, plan: DecompositionPlan, case_dir: str) -> "ExecutionSession":
        """Initialize a new execution session from a decomposition plan.

        All sub-goals start as 'pending'. Those with unmet dependencies
        (deps that aren't completed yet) are set to 'blocked' immediately,
        which is the state for "waiting on predecessor".
        """
        state: Dict[str, str] = {}
        blocked_reasons: Dict[str, str] = {}

        for sg_id, sg in plan.sub_goals.items():
            unmet = [d for d in sg.dependencies if d not in plan.sub_goals]
            if unmet:
                state[sg_id] = "blocked"
                blocked_reasons[sg_id] = f"依赖缺失: {', '.join(unmet)}"
            else:
                state[sg_id] = "pending"

        # Level 0 (shared context) has no deps, so it starts pending.
        # Sub-goals whose dependencies are all in the plan start pending too.
        # They'll be naturally ordered by next_ready() which respects topo groups.

        session = cls(
            plan=plan,
            state=state,
            findings={sg_id: [] for sg_id in plan.sub_goals},
            case_dir=os.path.abspath(case_dir),
            started_at=_now(),
            blocked_reasons=blocked_reasons,
        )
        session.allocate_all()
        return session

    @classmethod
    def load(cls, path: str, plan_path: Optional[str] = None) -> "ExecutionSession":
        """Load a session from session_state.json.

        Args:
            path: Path to session_state.json.
            plan_path: Override plan path. If None, uses the path in the session file.

        Returns:
            Reconstructed ExecutionSession.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        actual_plan_path = plan_path or data.get("plan_path", "")
        if actual_plan_path and not os.path.isabs(actual_plan_path):
            actual_plan_path = os.path.join(os.path.dirname(path), actual_plan_path)

        plan = _load_plan(actual_plan_path) if actual_plan_path else DecompositionPlan(
            challenge_name=data.get("challenge_name", "Unknown")
        )

        session = cls(
            plan=plan,
            state=data.get("state", {}),
            findings=data.get("findings", {}),
            current_sg_id=data.get("current_sg_id"),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            case_dir=data.get("case_dir", ""),
            blocked_reasons=data.get("blocked_reasons", {}),
            boost_mode=data.get("boost_mode", False),
            boost_results=data.get("boost_results", {}),
            allocations=data.get("allocations", {}),
            allocation_overrides=data.get("allocation_overrides", {}),
        )

        # Validate: warn if plan structure changed
        new_ids = set(plan.sub_goals.keys())
        old_ids = set(session.state.keys())
        if new_ids != old_ids:
            added = new_ids - old_ids
            removed = old_ids - new_ids
            if added:
                for sid in added:
                    session.state[sid] = "pending"
                    session.findings[sid] = []
            if removed:
                for sid in removed:
                    session.state.pop(sid, None)
                    session.findings.pop(sid, None)

        return session

    # ── State Queries ────────────────────────────────────────────

    def next_ready(self) -> List[str]:
        """Return sub-goal IDs that are ready to execute.

        Only returns IDs from the earliest topological group that has
        any ready sub-goals — enforces topological discipline.

        A sub-goal is ready when:
        - state is 'pending'
        - all its dependencies are 'completed'

        If a sub-goal is currently in focus, only that ID is returned.
        """
        if self.current_sg_id:
            return [self.current_sg_id]

        # Find all sub-goals whose deps are all completed and state is pending
        ready_ids = [
            sg_id for sg_id, sg in self.plan.sub_goals.items()
            if self.state.get(sg_id) == "pending"
            and all(self.state.get(d) == "completed" for d in sg.dependencies)
        ]

        if not ready_ids:
            return []

        # Group by topological level
        for group in self.plan.topological_order:
            group_ready = [sid for sid in group if sid in ready_ids]
            if group_ready:
                # Sort by priority (lower = more urgent), then by estimated time (shorter first)
                group_ready.sort(key=lambda sid: (
                    self.plan.sub_goals[sid].priority,
                    self.plan.sub_goals[sid].estimated_minutes,
                ))
                return group_ready

        return ready_ids

    def is_complete(self) -> bool:
        """Check if ALL sub-goals are completed."""
        return all(s == "completed" for s in self.state.values())

    def is_all_blocked(self) -> bool:
        """Check if all remaining (non-completed) sub-goals are blocked."""
        remaining = [sid for sid, s in self.state.items() if s != "completed"]
        return all(self.state[sid] == "blocked" for sid in remaining)

    # ── State Transitions ────────────────────────────────────────

    def focus(self, sg_id: str) -> dict:
        """Set a sub-goal as in_focus and return its execution context.

        The context dict contains everything the AI needs for Phase 2
        (correlation analysis) per the focused_execution.md protocol.

        Raises ValueError if another sub-goal is already in focus.
        """
        if self.current_sg_id and self.current_sg_id != sg_id:
            raise ValueError(
                f"无法聚焦 {sg_id}，当前已聚焦于 {self.current_sg_id}。"
                f"请先完成或阻塞当前目标。"
            )

        sg = self.plan.sub_goals.get(sg_id)
        if not sg:
            raise ValueError(f"子目标不存在: {sg_id}")

        self.state[sg_id] = "in_focus"
        self.current_sg_id = sg_id

        # Gather dependency findings
        dep_findings: Dict[str, list] = {}
        for dep_id in sg.dependencies:
            if dep_id in self.findings and self.findings[dep_id]:
                dep_findings[dep_id] = self.findings[dep_id]

        # Build KB search terms from domain + task_type
        kb_terms = _build_kb_terms(sg)

        return {
            "sg_id": sg_id,
            "description": sg.description,
            "domain": sg.domain,
            "task_type": sg.task_type,
            "level": sg.level,
            "level_name": {0: "共享上下文", 1: "检材准备", 2: "领域分析", 3: "题目解答"}.get(sg.level, f"L{sg.level}"),
            "tools": sg.tools,
            "inputs": sg.inputs,
            "outputs": sg.outputs,
            "dependencies": sg.dependencies,
            "estimated_minutes": sg.estimated_minutes,
            "priority": sg.priority,
            "assigned_role": sg.assigned_role,
            "answer_format": sg.answer_format,
            "question_text": sg.question_text,
            "dep_findings": dep_findings,
            "kb_search_terms": kb_terms,
            "completed_count": sum(1 for s in self.state.values() if s == "completed"),
            "total_count": len(self.plan.sub_goals),
        }

    def complete(self, sg_id: str, findings_list: Optional[list] = None) -> List[str]:
        """Mark a sub-goal as completed and auto-unblock its dependents.

        Args:
            sg_id: Sub-goal ID to mark complete.
            findings_list: List of finding dicts to store.

        Returns:
            List of sub-goal IDs that were unblocked by this completion.
        """
        if findings_list:
            self.findings[sg_id] = findings_list

        self.state[sg_id] = "completed"
        self.blocked_reasons.pop(sg_id, None)

        if self.current_sg_id == sg_id:
            self.current_sg_id = None

        # Auto-unblock: any sub-goal whose deps are now all completed
        unblocked = []
        for other_id, other in self.plan.sub_goals.items():
            if self.state.get(other_id) == "blocked":
                if all(self.state.get(d) == "completed" for d in other.dependencies):
                    self.state[other_id] = "pending"
                    self.blocked_reasons.pop(other_id, None)
                    unblocked.append(other_id)

        if self.is_complete():
            self.completed_at = _now()

        return unblocked

    def block(self, sg_id: str, reason: str) -> None:
        """Mark a sub-goal as blocked with a reason.

        Does NOT unblock this sub-goal's dependents — they stay blocked
        until this sub-goal is eventually completed.
        """
        self.state[sg_id] = "blocked"
        self.blocked_reasons[sg_id] = reason

        if self.current_sg_id == sg_id:
            self.current_sg_id = None

    # ── Boost Mode ────────────────────────────────────────────────

    def enable_boost(self) -> None:
        """Enable weak model boost mode for this session."""
        self.boost_mode = True

    def get_boost_context(self, sg_id: Optional[str] = None) -> dict:
        """Get context dict optimized for BoostOrchestrator.

        If sg_id is None, uses the next ready sub-goal.
        Returns a dict suitable for BoostOrchestrator.execute().
        """
        target_id = sg_id or (self.next_ready()[0] if self.next_ready() else None)
        if not target_id:
            raise ValueError("没有就绪的子目标")

        context = self.focus(target_id)
        self.save()
        return context

    def record_boost_result(self, sg_id: str, result: dict) -> None:
        """Store boost result and, if successful, complete the sub-goal.

        If boost FAILED: auto-reallocate to FOCUSED + lower priority
        so easier sub-goals are attempted first (dynamic priority).
        """
        self.boost_results[sg_id] = result

        if result.get("success"):
            findings = result.get("findings", [])
            if result.get("answer"):
                findings.append({
                    "tool": "boost_orchestrator",
                    "finding": result["answer"],
                    "evidence": result.get("evidence_path", ""),
                    "confidence": result.get("confidence", "placeholder"),
                    "method": result.get("method", "unknown"),
                })
            self.complete(sg_id, findings)
        else:
            # Dynamic priority: boost failed → reallocate to FOCUSED, lower priority
            self.block(sg_id, result.get("error", "Boost pipeline failed"))
            self.reallocate(sg_id, "focused")

        self.save()

    # ── Allocation Mode ────────────────────────────────────────────

    def kb_root(self) -> str:
        """Return resolved KB root path."""
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "knowledge"
        )

    def allocate_all(self, config=None) -> "AllocationPlan":
        """Batch-allocate all sub-goals. Returns AllocationPlan with summary."""
        from tools.decomposer.allocator import allocate_all, AllocationConfig

        cfg = config or AllocationConfig()
        plan = allocate_all(self.plan, self.findings, self.kb_root(), cfg)

        # Apply manual overrides
        for sg_id, forced_mode in self.allocation_overrides.items():
            if sg_id in plan.allocations:
                from tools.decomposer.allocator import AllocationMode
                plan.allocations[sg_id].mode = AllocationMode(forced_mode)
                plan.allocations[sg_id].overridden = True

        self.allocations = {
            sg_id: a.to_dict() for sg_id, a in plan.allocations.items()
        }
        self.save()
        return plan

    def next_ready_with_allocation(self) -> dict:
        """Like next_ready() but merges allocation info into the context.

        Allocates JIT if the sub-goal hasn't been allocated yet.
        """
        ready = self.next_ready()

        if not ready:
            if self.is_complete():
                return {"status": "all_complete", "completed_at": self.completed_at}
            if self.is_all_blocked():
                return {
                    "status": "all_blocked",
                    "blocked": [
                        {"sg_id": sid, "reason": self.blocked_reasons.get(sid, "")}
                        for sid, s in self.state.items() if s == "blocked"
                    ],
                }
            return {"status": "no_ready", "message": "No ready sub-goals but some pending"}

        sg_id = ready[0]

        # JIT allocate if not already done
        if sg_id not in self.allocations:
            from tools.decomposer.allocator import allocate_one
            sg = self.plan.sub_goals.get(sg_id)
            if sg:
                dep_findings = {
                    dep_id: self.findings.get(dep_id, [])
                    for dep_id in sg.dependencies
                }
                result = allocate_one(sg, self.plan, dep_findings, self.kb_root())
                self.allocations[sg_id] = result.to_dict()

        allocation = self.allocations.get(sg_id, {})

        try:
            context = self.focus(sg_id)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        context["allocation_mode"] = allocation.get("mode", "focused")
        context["allocation_score"] = allocation.get("complexity_score", 0.0)
        context["allocation_reason"] = allocation.get("reason", "")
        context["allocation_kb_match"] = allocation.get("kb_match_found", False)
        context["allocation_overridden"] = allocation.get("overridden", False)

        self.save()
        return context

    def reallocate(self, sg_id: str, force_mode: Optional[str] = None) -> dict:
        """Re-assign a sub-goal's mode. Auto-promotes failed boost to FOCUSED
        and lowers priority so easier tasks go first.

        Args:
            sg_id: Sub-goal to reallocate.
            force_mode: If given, forces this mode. If None, auto-scores.
        """
        from tools.decomposer.allocator import allocate_one, AllocationMode

        sg = self.plan.sub_goals.get(sg_id)
        if not sg:
            raise ValueError(f"子目标不存在: {sg_id}")

        prev = self.allocations.get(sg_id, {})

        if force_mode:
            self.allocation_overrides[sg_id] = force_mode
        else:
            # Auto-promote: if previously BOOST and now blocked, go FOCUSED
            prev_mode = prev.get("mode", "")
            if prev_mode == "boost" and self.state.get(sg_id) == "blocked":
                force_mode = "focused"
                self.allocation_overrides[sg_id] = "focused"

        dep_findings = {
            dep_id: self.findings.get(dep_id, [])
            for dep_id in sg.dependencies
        }
        result = allocate_one(sg, self.plan, dep_findings, self.kb_root())

        if force_mode:
            result.mode = AllocationMode(force_mode)
            result.overridden = True
            result.reason = f"手动覆盖 → {force_mode}"

        self.allocations[sg_id] = result.to_dict()

        # Dynamic priority: if reallocating to FOCUSED due to boost failure,
        # lower priority so easier sub-goals go first
        if force_mode == "focused" and prev.get("mode") == "boost":
            sg.priority += 2
            result.reason += f" | priority={sg.priority}"

        # Unblock if it was blocked
        if self.state.get(sg_id) == "blocked":
            self.state[sg_id] = "pending"
            self.blocked_reasons.pop(sg_id, None)

        self.save()
        return result.to_dict()

    # ── Status ────────────────────────────────────────────────────

    def status(self) -> str:
        """Human-readable progress summary."""
        total = len(self.plan.sub_goals)
        completed = sum(1 for s in self.state.values() if s == "completed")
        in_focus = sum(1 for s in self.state.values() if s == "in_focus")
        blocked = sum(1 for s in self.state.values() if s == "blocked")
        pending = sum(1 for s in self.state.values() if s == "pending")
        ready = len(self.next_ready())

        mode_str = " [超频模式]" if self.boost_mode else ""
        lines = [
            f"执行会话: {self.plan.challenge_name}{mode_str}",
            f"进度: {completed}/{total} 完成",
        ]
        if in_focus:
            sg = self.plan.sub_goals.get(self.current_sg_id or "")
            desc = sg.description[:60] if sg else "?"
            lines.append(f"当前聚焦: {self.current_sg_id} - {desc}")
        lines.append(f"就绪: {ready} | 待处理: {pending} | 阻塞: {blocked} | 已完成: {completed}")
        lines.append(f"开始: {self.started_at}")

        if self.completed_at:
            lines.append(f"完成: {self.completed_at}")
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)

        ready_ids = self.next_ready()
        if ready_ids and not self.current_sg_id:
            lines.append(f"就绪队列: {', '.join(ready_ids[:5])}")
            if len(ready_ids) > 5:
                lines.append(f"  ... 还有 {len(ready_ids) - 5} 个")

        blocked_ids = [sid for sid, s in self.state.items() if s == "blocked"]
        if blocked_ids:
            lines.append("阻塞项:")
            for bid in blocked_ids[:5]:
                reason = self.blocked_reasons.get(bid, "未知")
                lines.append(f"  {bid}: {reason[:80]}")

        # Critical path progress
        if self.plan.critical_path:
            cp_done = [sid for sid in self.plan.critical_path if self.state.get(sid) == "completed"]
            lines.append(f"关键路径: {len(cp_done)}/{len(self.plan.critical_path)} 完成")

        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        """Save session to session_state.json.

        Args:
            path: Output path. Defaults to {case_dir}/session_state.json.

        Returns:
            The saved file path.
        """
        if path is None:
            path = os.path.join(self.case_dir, "session_state.json")

        data = {
            "plan_path": os.path.join(self.case_dir, "execution_plan.json"),
            "challenge_name": self.plan.challenge_name,
            "case_dir": self.case_dir,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_sg_id": self.current_sg_id,
            "state": self.state,
            "findings": self.findings,
            "blocked_reasons": self.blocked_reasons,
            "boost_mode": self.boost_mode,
            "boost_results": self.boost_results,
            "allocations": self.allocations,
            "allocation_overrides": self.allocation_overrides,
        }

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return path


# ── Helpers ───────────────────────────────────────────────────────

def _load_plan(path: str) -> DecompositionPlan:
    """Reconstruct a DecompositionPlan from execution_plan.json."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from tools.decomposer.models import EvidenceInfo, SubGoal

    plan = DecompositionPlan(
        challenge_name=data.get("challenge_name", "Unknown"),
        created_at=data.get("created_at", ""),
        critical_path=data.get("critical_path", []),
        critical_path_minutes=data.get("critical_path_minutes", 0),
    )

    groups = data.get("groups", [])
    topo_order = []
    for group in groups:
        group_ids = []
        for sg_data in group.get("sub_goals", []):
            sg_id = sg_data["id"]
            group_ids.append(sg_id)

            sg = SubGoal(
                id=sg_id,
                level=sg_data.get("level", 2),
                description=sg_data.get("description", ""),
                domain=sg_data.get("task_type", "").replace("_analysis", ""),
                task_type=sg_data.get("task_type", ""),
                inputs=sg_data.get("inputs", []),
                outputs=sg_data.get("outputs", []),
                dependencies=_infer_deps(sg_id, data),
                tools=sg_data.get("tools", []),
                assigned_role=sg_data.get("assigned_role", ""),
                estimated_minutes=sg_data.get("estimated_minutes", 30),
                priority=4 if sg_data.get("level") == 3 else sg_data.get("level", 2) + 1,
            )
            plan.sub_goals[sg_id] = sg

        topo_order.append(group_ids)

    plan.topological_order = topo_order

    # Infer role assignments from groups
    for group in groups:
        for sg_data in group.get("sub_goals", []):
            role = sg_data.get("assigned_role", "")
            if role:
                plan.role_assignments.setdefault(role, []).append(sg_data["id"])

    return plan


def _infer_deps(sg_id: str, plan_data: dict) -> List[str]:
    """Infer dependencies from the group structure in execution_plan.json."""
    groups = plan_data.get("groups", [])
    current_group_idx = -1

    for i, group in enumerate(groups):
        for sg_data in group.get("sub_goals", []):
            if sg_data["id"] == sg_id:
                current_group_idx = i
                break
        if current_group_idx >= 0:
            break

    if current_group_idx <= 0:
        return []

    # Depend on all sub-goals from previous groups
    deps = []
    for i in range(current_group_idx):
        for sg_data in groups[i].get("sub_goals", []):
            deps.append(sg_data["id"])
    return deps


def _build_kb_terms(sg: SubGoal) -> List[str]:
    """Build KB search terms from a sub-goal's domain and task_type."""
    terms = []
    if sg.domain:
        terms.append(sg.domain)
    if sg.task_type:
        clean = sg.task_type.replace("_analysis", "").replace("_", " ")
        if clean not in terms:
            terms.append(clean)
    # Add domain-specific keywords
    domain_kw = {
        "memory": ["volatility", "进程", "内存"],
        "disk": ["filesystem", "磁盘", "mount"],
        "network": ["pcap", "tshark", "流量"],
        "mobile": ["android", "ios", "手机"],
        "binary": ["reverse", "逆向", "ida"],
        "stego": ["隐写", "lsb", "binwalk"],
        "crypto": ["密码", "解密", "rsa"],
        "log": ["日志", "event", "evtx"],
    }
    for kw in domain_kw.get(sg.domain, []):
        if kw not in terms:
            terms.append(kw)
    return terms
