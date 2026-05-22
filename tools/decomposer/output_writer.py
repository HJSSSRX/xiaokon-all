"""Output writer for decomposition plans.

Generates:
1. decomposition_report.md — Mermaid dependency graph + execution plan tables
2. tasks.json — Compatible with SmartScheduler
3. execution_plan.json — Parallel execution groups with role assignments
"""

import json
import os
from typing import Dict, Optional

from tools.decomposer.models import DecompositionPlan, SubGoalLevel


LEVEL_NAMES = {
    0: "共享上下文",
    1: "检材准备",
    2: "领域分析",
    3: "题目解答",
}

LEVEL_ICONS = {
    0: "[L0]",
    1: "[L1]",
    2: "[L2]",
    3: "[L3]",
}


def write_report(plan: DecompositionPlan, output_path: str) -> str:
    """Generate a markdown decomposition report.

    Returns the path to the written report.
    """
    lines = [
        f"# 题目分解报告: {plan.challenge_name}",
        "",
        f"**生成时间**: {plan.created_at}",
        f"**题目描述**: {plan.challenge_description[:200]}",
        "",
        "---",
        "",
        "## 概览",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 检材文件数 | {len(plan.evidence_files)} |",
        f"| 子目标总数 | {len(plan.sub_goals)} |",
        f"| 并行组数 | {len(plan.topological_order)} |",
        f"| 关键路径 | {len(plan.critical_path)} 个子目标, 估计 {plan.critical_path_minutes} 分钟 |",
    ]

    # Evidence summary
    if plan.evidence_files:
        total_size = sum(e.size_bytes for e in plan.evidence_files)
        gb = total_size / (1024 ** 3)
        lines.append(f"| 检材总大小 | {gb:.1f} GB |")
    lines.append("")

    # Evidence table
    if plan.evidence_files:
        lines.append("## 检材清单")
        lines.append("")
        lines.append("| 文件 | 大小 | 类型 | 需要准备 |")
        lines.append("|------|------|------|----------|")
        for ev in plan.evidence_files:
            size_str = _format_size(ev.size_bytes)
            prep = []
            if ev.mount_required:
                prep.append("挂载")
            if ev.is_encrypted:
                prep.append("解密")
            if ev.is_archive:
                prep.append("解压")
            prep_str = ", ".join(prep) if prep else "—"
            lines.append(f"| {ev.path} | {size_str} | {ev.detected_type} | {prep_str} |")
        lines.append("")

    # Dependency graph (Mermaid)
    lines.append("## 依赖关系图")
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph TD")
    for sg_id, sg in plan.sub_goals.items():
        short_desc = sg.description[:40].replace('"', "'")
        level_label = LEVEL_ICONS.get(sg.level, "")
        node_label = f"{sg_id}<br/>{level_label} {short_desc}"
        lines.append(f'    {sg_id}["{node_label}"]')
    for sg_id, sg in plan.sub_goals.items():
        for dep_id in sg.dependencies:
            lines.append(f"    {dep_id} --> {sg_id}")
    lines.append("```")
    lines.append("")

    # Execution plan
    lines.append("## 执行计划")
    lines.append("")
    for i, group in enumerate(plan.topological_order):
        lines.append(f"### 第 {i + 1} 组 (可并行执行)")
        lines.append("")
        lines.append("| 子目标 | 层级 | 描述 | 角色 | 预估 | 工具 |")
        lines.append("|--------|------|------|------|------|------|")
        for sg_id in group:
            sg = plan.sub_goals.get(sg_id)
            if not sg:
                continue
            level_str = LEVEL_NAMES.get(sg.level, f"L{sg.level}")
            role = sg.assigned_role or "未分配"
            tools = ", ".join(sg.tools[:3]) if sg.tools else "—"
            lines.append(
                f"| {sg_id} | {level_str} | {sg.description[:60]} | "
                f"{role} | {sg.estimated_minutes}min | {tools} |"
            )
        lines.append("")

    # Critical path
    lines.append("## 关键路径")
    lines.append("")
    path_str = " → ".join(plan.critical_path)
    lines.append(f"**路径**: {path_str}")
    lines.append(f"**估计总时间**: {plan.critical_path_minutes} 分钟")
    lines.append("")
    lines.append("| 子目标 | 描述 | 预估 |")
    lines.append("|--------|------|------|")
    for sg_id in plan.critical_path:
        sg = plan.sub_goals.get(sg_id)
        if sg:
            lines.append(f"| {sg_id} | {sg.description[:60]} | {sg.estimated_minutes}min |")
    lines.append("")

    # Role assignments summary
    if plan.role_assignments:
        lines.append("## 角色分配")
        lines.append("")
        lines.append("| 角色 | 子目标数 | 子目标 |")
        lines.append("|------|----------|--------|")
        for role, sg_ids in plan.role_assignments.items():
            lines.append(f"| {role} | {len(sg_ids)} | {', '.join(sg_ids)} |")
        lines.append("")

    # Tool recommendations
    if plan.tool_recommendations:
        lines.append("## 工具推荐 (来自知识库关联规则挖掘)")
        lines.append("")
        for sg_id, tools in plan.tool_recommendations.items():
            sg = plan.sub_goals.get(sg_id)
            if sg and tools:
                lines.append(f"- **{sg_id}** ({sg.description[:50]}): {', '.join(tools[:5])}")
        lines.append("")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return output_path


def write_tasks_json(plan: DecompositionPlan, output_path: str) -> str:
    """Generate tasks.json compatible with SmartScheduler.

    Returns the path to the written file.
    """
    tasks: Dict[str, dict] = {}

    # Level → difficulty mapping
    difficulty_map = {0: 1, 1: 2, 2: 3, 3: 2}

    for sg_id, sg in plan.sub_goals.items():
        tasks[sg_id] = {
            "type": sg.task_type or "data_recovery",
            "description": sg.description,
            "difficulty": difficulty_map.get(sg.level, 2),
            "evidence_path": sg.inputs[0] if sg.inputs else "",
            "priority": sg.priority,
            "dependencies": sg.dependencies,
            "estimated_time_minutes": sg.estimated_minutes,
            "assigned_role": sg.assigned_role,
            "status": "pending",
            "progress": 0,
            "result": None,
        }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

    return output_path


def write_execution_plan(plan: DecompositionPlan, output_path: str) -> str:
    """Generate execution_plan.json with ordered parallel groups.

    Returns the path to the written file.
    """
    groups = []
    for i, group_ids in enumerate(plan.topological_order):
        sub_goals_list = []
        total_minutes = 0
        roles = set()

        for sg_id in group_ids:
            sg = plan.sub_goals.get(sg_id)
            if not sg:
                continue
            sub_goals_list.append({
                "id": sg_id,
                "description": sg.description,
                "level": sg.level,
                "level_name": LEVEL_NAMES.get(sg.level, f"L{sg.level}"),
                "task_type": sg.task_type,
                "assigned_role": sg.assigned_role or "unassigned",
                "estimated_minutes": sg.estimated_minutes,
                "tools": sg.tools[:5],
                "inputs": sg.inputs,
                "outputs": sg.outputs,
            })
            total_minutes = max(total_minutes, sg.estimated_minutes)
            if sg.assigned_role:
                roles.add(sg.assigned_role)

        groups.append({
            "group_id": i + 1,
            "sub_goals": sub_goals_list,
            "estimated_duration_minutes": total_minutes,
            "roles_involved": sorted(roles),
            "parallelizable": len(sub_goals_list) > 1,
        })

    plan_dict = {
        "challenge_name": plan.challenge_name,
        "created_at": plan.created_at,
        "total_sub_goals": len(plan.sub_goals),
        "total_parallel_groups": len(groups),
        "critical_path_minutes": plan.critical_path_minutes,
        "critical_path": plan.critical_path,
        "groups": groups,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plan_dict, f, indent=2, ensure_ascii=False)

    return output_path


def write_all_outputs(
    plan: DecompositionPlan,
    output_dir: str,
    prefix: str = "",
) -> Dict[str, str]:
    """Write all output formats to an output directory.

    Args:
        plan: The decomposition plan to output.
        output_dir: Directory to write outputs into.
        prefix: Optional filename prefix.

    Returns:
        {output_type: file_path} mapping.
    """
    os.makedirs(output_dir, exist_ok=True)

    p = f"{prefix}_" if prefix else ""

    outputs = {}
    outputs["report"] = write_report(
        plan, os.path.join(output_dir, f"{p}decomposition_report.md")
    )
    outputs["tasks_json"] = write_tasks_json(
        plan, os.path.join(output_dir, f"{p}tasks.json")
    )
    outputs["execution_plan"] = write_execution_plan(
        plan, os.path.join(output_dir, f"{p}execution_plan.json")
    )

    return outputs


def format_summary(plan: DecompositionPlan) -> str:
    """Return a short text summary suitable for terminal output."""
    n_evidence = len(plan.evidence_files)
    n_goals = len(plan.sub_goals)
    n_groups = len(plan.topological_order)
    types = set(e.detected_type for e in plan.evidence_files if e.detected_type != "unknown")
    roles = list(plan.role_assignments.keys()) if plan.role_assignments else []

    lines = [
        f"题目: {plan.challenge_name}",
        f"检材: {n_evidence} 个文件, 类型: {', '.join(sorted(types)) if types else '无'}",
        f"子目标: {n_goals} 个, {n_groups} 个并行组",
        f"关键路径: {' → '.join(plan.critical_path[:5])}{'...' if len(plan.critical_path) > 5 else ''} ({plan.critical_path_minutes}min)",
        f"角色: {', '.join(roles) if roles else '未分配'}",
    ]

    # Show execution groups
    for i, group in enumerate(plan.topological_order[:5]):
        ids = ", ".join(group[:5])
        if len(group) > 5:
            ids += f" ... (+{len(group) - 5})"
        lines.append(f"  组{i + 1}: {ids}")

    if len(plan.topological_order) > 5:
        lines.append(f"  ... 共 {len(plan.topological_order)} 组")

    return "\n".join(lines)


def _format_size(size_bytes: int) -> str:
    """Format a byte count for human display."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.1f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"
