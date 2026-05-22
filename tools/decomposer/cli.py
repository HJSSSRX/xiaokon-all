"""CLI interface for the challenge decomposer.

Usage:
  python -m tools.cli decompose --dir <case_dir> [--output DIR] [--dry-run] [--verbose]
  python -m tools.cli decompose --text "<challenge description>" [--output DIR]
  python -m tools.cli decompose --stdin [--output DIR]
"""

import argparse
import os
import sys

from tools.decomposer import Decomposer
from tools.decomposer.output_writer import write_all_outputs, format_summary


def cmd_decompose(args):
    """Run challenge decomposition from CLI arguments."""
    # Determine input source
    challenge_dir = getattr(args, "dir", "")
    challenge_text = getattr(args, "text", "")
    use_stdin = getattr(args, "stdin", False)
    output_dir = getattr(args, "output", "")
    kb_root = getattr(args, "kb_root", "")
    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)

    if use_stdin:
        challenge_text = sys.stdin.read()
        if verbose:
            print(f"从 stdin 读取 {len(challenge_text)} 字符", file=sys.stderr)

    if not challenge_dir and not challenge_text:
        print("ERROR: 需要 --dir, --text, 或 --stdin 参数", file=sys.stderr)
        return

    if verbose:
        print(f"初始化 Decomposer (KB: {kb_root or '默认路径'})", file=sys.stderr)

    dec = Decomposer(
        kb_root=kb_root or "",
        recommend_tools=not getattr(args, "no_recommend", False),
    )

    if verbose:
        print("正在分解...", file=sys.stderr)

    plan = dec.decompose(
        challenge_dir=challenge_dir,
        challenge_text=challenge_text,
        output_dir="" if dry_run else (output_dir or challenge_dir or "."),
    )

    # Always print summary
    print(format_summary(plan))

    if not dry_run:
        out_dir = output_dir or challenge_dir or "."
        outputs = write_all_outputs(plan, out_dir)
        print(f"\n输出文件:")
        for name, path in outputs.items():
            print(f"  {name}: {path}")
    else:
        print("\n[干跑模式 — 未写入文件]")

    # Verbose: show full execution plan
    if verbose:
        print("\n=== 详细执行计划 ===")
        for i, group in enumerate(plan.topological_order):
            print(f"\n--- 第 {i + 1} 组 ({len(group)} 个子目标, 可并行) ---")
            for sg_id in group:
                sg = plan.sub_goals.get(sg_id)
                if not sg:
                    continue
                deps = f" 依赖: {', '.join(sg.dependencies)}" if sg.dependencies else ""
                tools = f" 工具: {', '.join(sg.tools[:5])}" if sg.tools else ""
                print(f"  {sg_id}: {sg.description}")
                print(f"    角色: {sg.assigned_role or '未分配'}, "
                      f"预估: {sg.estimated_minutes}min, 类型: {sg.task_type}{deps}{tools}")

        if plan.role_assignments:
            print("\n=== 角色负载 ===")
            for role, sg_ids in plan.role_assignments.items():
                total_min = sum(
                    plan.sub_goals[sg_id].estimated_minutes
                    for sg_id in sg_ids if sg_id in plan.sub_goals
                )
                print(f"  {role}: {len(sg_ids)} 个子目标, 共 {total_min}min")


def main():
    parser = argparse.ArgumentParser(
        prog="forensic decompose",
        description="自动分解题目为子目标依赖图，节省算力",
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--dir", "-d",
        help="题目目录路径 (包含检材 + 可选 challenge.md/questions.yaml)",
    )
    input_group.add_argument(
        "--text", "-t",
        help="自然语言题目描述",
    )
    input_group.add_argument(
        "--stdin", action="store_true",
        help="从 stdin 读取题目描述",
    )

    parser.add_argument("--output", "-o", help="输出目录 (默认: 题目目录或当前目录)")
    parser.add_argument("--kb-root", help="知识库根路径 (默认: 自动检测)")
    parser.add_argument("--no-recommend", action="store_true", help="跳过工具推荐 (更快)")
    parser.add_argument("--dry-run", "-n", action="store_true", help="干跑模式, 不写文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    args = parser.parse_args()
    cmd_decompose(args)


if __name__ == "__main__":
    main()
