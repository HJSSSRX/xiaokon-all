"""CLI wrapper for ExecutionSession.

Provides subcommands for the focused execution loop:
  start    — Initialize a new execution session
  status   — Print human-readable progress
  next     — Print JSON context for next ready sub-goal (AI protocol)
  complete — Mark a sub-goal complete with findings
  block    — Mark a sub-goal as blocked with reason
  boost    — Weak model boost — 6-step amplification pipeline
  allocate — Auto-allocate BOOST/FOCUSED mode per sub-goal
"""

import argparse
import json
import os
import sys


def _get_session(args):
    """Load session from case_dir/session_state.json."""
    from tools.decomposer.session import ExecutionSession

    case_dir = getattr(args, "case_dir", ".")
    state_path = os.path.join(case_dir, "session_state.json")
    if not os.path.exists(state_path):
        print(f"ERROR: 会话文件不存在: {state_path}", file=sys.stderr)
        print(f"请先运行: python -m tools.cli executor start --plan <path> --case-dir <dir>", file=sys.stderr)
        sys.exit(1)
    return ExecutionSession.load(state_path)


def cmd_start(args):
    """Initialize a new execution session."""
    from tools.decomposer.session import ExecutionSession, _load_plan

    plan_path = getattr(args, "plan", "")
    case_dir = getattr(args, "case_dir", ".")

    if not plan_path:
        print("ERROR: 需要 --plan 参数", file=sys.stderr)
        return

    if not os.path.exists(plan_path):
        print(f"ERROR: 计划文件不存在: {plan_path}", file=sys.stderr)
        return

    plan = _load_plan(plan_path)
    session = ExecutionSession.start(plan, case_dir)
    session.save()

    print(f"会话已启动: {plan.challenge_name}")
    print(f"子目标总数: {len(plan.sub_goals)}")

    # Show allocation summary
    boost_n = sum(1 for a in session.allocations.values() if a.get("mode") == "boost")
    focused_n = sum(1 for a in session.allocations.values() if a.get("mode") == "focused")
    if boost_n + focused_n > 0:
        print(f"分配: BOOST={boost_n}, FOCUSED={focused_n}")

    ready = session.next_ready()
    print(f"就绪: {len(ready)} 个")

    if ready:
        print("就绪队列:")
        for sg_id in ready[:8]:
            sg = plan.sub_goals.get(sg_id)
            if sg:
                level_name = {0: "共享", 1: "准备", 2: "分析", 3: "题目"}.get(sg.level, f"L{sg.level}")
                print(f"  {sg_id} [{level_name}] {sg.description[:60]} ({sg.estimated_minutes}min → {sg.assigned_role or '?'})")

    print(f"\n会话已保存: {os.path.join(os.path.abspath(case_dir), 'session_state.json')}")


def cmd_status(args):
    """Print execution progress."""
    session = _get_session(args)
    print(session.status())


def cmd_next(args):
    """Print JSON context for the next ready sub-goal.

    This is the primary command used by the AI during Phase 1 of the
    focused_execution.md protocol. Output is JSON for machine consumption.

    Allocation mode is automatically included — the AI reads allocation_mode
    to decide whether to use focused_execution.md or weak_model_boost.md.
    """
    session = _get_session(args)
    context = session.next_ready_with_allocation()
    print(json.dumps(context, indent=2, ensure_ascii=False))


def cmd_complete(args):
    """Mark a sub-goal as complete."""
    session = _get_session(args)
    sg_id = getattr(args, "sg_id", "")

    if not sg_id:
        print("ERROR: 需要 --sg-id 参数", file=sys.stderr)
        return

    findings_raw = getattr(args, "findings", "")
    findings = []
    if findings_raw:
        try:
            findings = json.loads(findings_raw)
        except json.JSONDecodeError:
            findings = [{"raw": findings_raw}]

    unblocked = session.complete(sg_id, findings)
    session.save()

    print(f"{sg_id} 已完成")
    if findings:
        print(f"  记录了 {len(findings)} 个发现")

    if unblocked:
        print(f"  解封了: {', '.join(unblocked)}")

    if session.is_complete():
        print("\n全部完成!")
        import winsound
        winsound.Beep(800, 300)

    ready = session.next_ready()
    if ready and not session.is_complete():
        print(f"下一个就绪: {', '.join(ready[:3])}")


def cmd_block(args):
    """Mark a sub-goal as blocked."""
    session = _get_session(args)
    sg_id = getattr(args, "sg_id", "")
    reason = getattr(args, "reason", "未指定原因")

    if not sg_id:
        print("ERROR: 需要 --sg-id 参数", file=sys.stderr)
        return

    session.block(sg_id, reason)
    session.save()

    print(f"{sg_id} 已阻塞: {reason}")

    ready = session.next_ready()
    if ready:
        print(f"下一个就绪: {', '.join(ready[:3])}")
    elif session.is_all_blocked():
        print("所有剩余子目标均已阻塞!")


def cmd_boost(args):
    """Run weak model boost pipeline on a sub-goal.

    Uses the BoostOrchestrator to execute the 6-step amplification
    pipeline: KB search → compact prompt → model inference →
    validation → retry → voting → escalation.
    """
    from tools.decomposer.session import ExecutionSession
    from tools.decomposer.boost import BoostOrchestrator, BoostConfig

    case_dir = getattr(args, "case_dir", ".")
    state_path = os.path.join(case_dir, "session_state.json")

    if not os.path.exists(state_path):
        print(f"ERROR: 会话文件不存在: {state_path}", file=sys.stderr)
        print(f"请先运行: python -m tools.cli executor start --plan <path> --case-dir <dir>", file=sys.stderr)
        sys.exit(1)

    session = ExecutionSession.load(state_path)
    session.enable_boost()

    sg_id = getattr(args, "sg_id", "")
    try:
        context = session.get_boost_context(sg_id if sg_id else None)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    target_sg_id = context["sg_id"]
    print(f"超频模式已激活 — 目标: {target_sg_id}")
    print(f"描述: {context.get('description', '?')[:80]}")
    print(f"领域: {context.get('domain', '?')} | 工具: {', '.join(context.get('tools', [])[:5])}")
    print()

    config = BoostConfig(
        kb_first=getattr(args, "kb_first", True),
        max_retries=getattr(args, "max_retries", 2),
        voting_samples=getattr(args, "voting_samples", 3),
        log_every_step=not getattr(args, "quiet", False),
    )

    orch = BoostOrchestrator(config=config)
    result = orch.execute(context, case_dir)

    # Record result
    result_dict = {
        "sg_id": result.sg_id,
        "success": result.success,
        "method": result.method,
        "commands": result.commands,
        "answer": result.answer,
        "confidence": result.confidence,
        "validation_errors": result.validation_errors,
        "attempts": result.attempts,
        "error": result.error,
        "timestamp": result.timestamp,
    }
    session.record_boost_result(target_sg_id, result_dict)

    # Print summary
    print()
    print("=" * 50)
    print(f"结果: {'[OK] 成功' if result.success else '[FAIL] 失败'}")
    print(f"方法: {result.method}")
    print(f"置信度: {result.confidence}")
    print(f"尝试次数: {result.attempts}")
    if result.answer:
        print(f"答案: {result.answer[:100]}")
    if result.commands:
        print(f"命令 ({len(result.commands)}):")
        for cmd in result.commands[:5]:
            print(f"  $ {cmd}")
    if result.validation_errors:
        print(f"验证错误: {result.validation_errors}")
    if result.error:
        print(f"错误: {result.error}")
    print("=" * 50)

    if result.success:
        if session.is_complete():
            print("\n全部完成!")
            import winsound
            winsound.Beep(800, 300)
        else:
            ready = session.next_ready()
            if ready:
                print(f"\n下一个就绪: {', '.join(ready[:3])}")


def cmd_allocate(args):
    """Auto-allocate BOOST/FOCUSED mode for all sub-goals.

    Scores each sub-goal across 9 dimensions, checks KB for exact matches,
    and assigns the optimal execution mode. Supports manual override.
    """
    from tools.decomposer.session import ExecutionSession, _load_plan
    from tools.decomposer.allocator import AllocationConfig

    case_dir = getattr(args, "case_dir", ".")
    plan_path = getattr(args, "plan", "")
    state_path = os.path.join(case_dir, "session_state.json")

    if os.path.exists(state_path):
        session = ExecutionSession.load(state_path)
    elif plan_path and os.path.exists(plan_path):
        plan = _load_plan(plan_path)
        session = ExecutionSession.start(plan, case_dir)
    else:
        print("ERROR: 需要 --plan 或已有的 session_state.json", file=sys.stderr)
        sys.exit(1)

    force_sg_id = getattr(args, "force_sg_id", "")
    force_mode = getattr(args, "force_mode", "")

    if force_sg_id and force_mode:
        result = session.reallocate(force_sg_id, force_mode)
        mode_label = "超频" if result["mode"] == "boost" else "聚焦"
        print(f"已覆盖: {force_sg_id} -> {mode_label}")
        print(f"  复杂度分数: {result['complexity_score']:.2f}")
        print(f"  原因: {result['reason'][:100]}")
        return

    config = AllocationConfig(
        boost_threshold=getattr(args, "boost_threshold", 0.40),
    )
    plan = session.allocate_all(config)

    mode_labels = {"boost": "超频", "focused": "聚焦"}
    print(f"分配方案: {plan.challenge_name}")
    print(f"子目标总数: {len(plan.allocations)}")
    print(f"  BOOST (超频): {plan.summary.get('boost', 0)}")
    print(f"  FOCUSED (聚焦): {plan.summary.get('focused', 0)}")
    print()

    sorted_allocs = sorted(
        plan.allocations.values(),
        key=lambda a: a.complexity_score, reverse=True,
    )
    for a in sorted_allocs:
        mode_label = mode_labels.get(a.mode.value, a.mode.value)
        kb_flag = " [KB匹配]" if a.kb_match_found else ""
        override_flag = " [手动]" if a.overridden else ""
        print(f"  {a.sg_id} [{mode_label}] score={a.complexity_score:.2f}{kb_flag}{override_flag}")
        print(f"    {a.reason[:100]}")

    print()
    print(f"会话已保存: {os.path.join(os.path.abspath(case_dir), 'session_state.json')}")


def main():
    parser = argparse.ArgumentParser(
        prog="forensic executor",
        description="聚焦执行引擎 — 逐个子目标深度分析",
    )
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="启动执行会话")
    p_start.add_argument("--plan", required=True, help="execution_plan.json 路径")
    p_start.add_argument("--case-dir", default=".", help="案件目录")

    p_status = sub.add_parser("status", help="查看执行进度")
    p_status.add_argument("--case-dir", default=".", help="案件目录")

    p_next = sub.add_parser("next", help="获取下一个就绪子目标的上下文 (JSON, 自动含分配模式)")
    p_next.add_argument("--case-dir", default=".", help="案件目录")

    p_complete = sub.add_parser("complete", help="标记子目标完成")
    p_complete.add_argument("--sg-id", required=True, help="子目标ID")
    p_complete.add_argument("--case-dir", default=".", help="案件目录")
    p_complete.add_argument("--findings", default="", help="发现的JSON列表")

    p_block = sub.add_parser("block", help="阻塞子目标")
    p_block.add_argument("--sg-id", required=True, help="子目标ID")
    p_block.add_argument("--reason", default="未指定原因", help="阻塞原因")
    p_block.add_argument("--case-dir", default=".", help="案件目录")

    p_boost = sub.add_parser("boost", help="弱模型超频 — 6步放大流水线")
    p_boost.add_argument("--sg-id", default="", help="子目标ID (默认: 下一个就绪)")
    p_boost.add_argument("--case-dir", default=".", help="案件目录")
    p_boost.add_argument("--no-kb-first", action="store_true", help="跳过KB优先搜索")
    p_boost.add_argument("--max-retries", type=int, default=2, help="最大重试次数")
    p_boost.add_argument("--voting-samples", type=int, default=3, help="投票采样数")
    p_boost.add_argument("--quiet", action="store_true", help="静默模式")

    p_allocate = sub.add_parser("allocate", help="自动分配执行模式 (BOOST/FOCUSED)")
    p_allocate.add_argument("--plan", default="", help="execution_plan.json 路径")
    p_allocate.add_argument("--case-dir", default=".", help="案件目录")
    p_allocate.add_argument("--force-sg-id", default="", help="强制覆盖指定子目标的模式")
    p_allocate.add_argument("--force-mode", default="", choices=["boost", "focused"],
                            help="强制模式")
    p_allocate.add_argument("--boost-threshold", type=float, default=0.40,
                            help="复杂度阈值 (低于此为BOOST)")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "next":
        cmd_next(args)
    elif args.command == "complete":
        cmd_complete(args)
    elif args.command == "block":
        cmd_block(args)
    elif args.command == "boost":
        cmd_boost(args)
    elif args.command == "allocate":
        cmd_allocate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
