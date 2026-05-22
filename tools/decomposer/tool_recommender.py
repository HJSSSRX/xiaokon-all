"""Tool recommendation wrapper around analytics.recommend.

Calls the existing Apriori-based recommendation engine to suggest tools
and knowledge domains for each sub-goal's context.
"""

import os
from typing import Dict, List, Optional

from tools.decomposer.models import SubGoal


def recommend_tools_for_sub_goals(
    sub_goals: Dict[str, SubGoal],
    kb_root: Optional[str] = None,
    top_n: int = 5,
) -> Dict[str, List[str]]:
    """Recommend tools for each analysis-level sub-goal.

    Uses the Apriori-based recommend() function from tools.analytics.

    Args:
        sub_goals: All sub-goals keyed by ID.
        kb_root: Knowledge base root directory.
        top_n: Number of tool recommendations per sub-goal.

    Returns:
        {sub_goal_id: [tool_names]} mapping.
    """
    if kb_root is None:
        kb_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "knowledge"
        )

    try:
        from tools.analytics.recommend import recommend
    except ImportError:
        return {}

    results: Dict[str, List[str]] = {}

    for sg_id, sg in sub_goals.items():
        # Build context: domain + task_type + evidence type
        context = []
        if sg.domain:
            context.append(sg.domain)
        if sg.task_type and sg.task_type not in context:
            context.append(sg.task_type.replace("_analysis", "").replace("_", " "))

        # Add evidence file extensions as context
        for inp in sg.inputs:
            ext = os.path.splitext(inp)[1]
            if ext:
                ctx = ext.lstrip(".")
                if ctx not in context:
                    context.append(ctx)

        if not context:
            continue

        try:
            rec = recommend(
                context,
                kb_root=kb_root,
                target="tools",
                min_support=0.08,
                min_confidence=0.3,
                min_lift=1.0,
                top_n=top_n,
            )
            tool_names = [r["item"] for r in rec.get("recommendations", [])]
            if tool_names:
                results[sg_id] = tool_names
        except Exception:
            continue

    return results


def recommend_kb_domains(
    sub_goals: Dict[str, SubGoal],
    kb_root: Optional[str] = None,
    top_n: int = 3,
) -> Dict[str, List[str]]:
    """Recommend knowledge base domains to search for each sub-goal.

    Uses the same recommend() engine with target="tags".

    Args:
        sub_goals: All sub-goals keyed by ID.
        kb_root: Knowledge base root directory.
        top_n: Number of tag recommendations per sub-goal.

    Returns:
        {sub_goal_id: [tag_names]} mapping.
    """
    if kb_root is None:
        kb_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "knowledge"
        )

    try:
        from tools.analytics.recommend import recommend
    except ImportError:
        return {}

    results: Dict[str, List[str]] = {}

    for sg_id, sg in sub_goals.items():
        context = [sg.domain] if sg.domain else []
        if sg.task_type:
            context.append(sg.task_type)

        if not context:
            continue

        try:
            rec = recommend(
                context,
                kb_root=kb_root,
                target="tags",
                min_support=0.08,
                min_confidence=0.3,
                top_n=top_n,
            )
            tag_names = [r["item"] for r in rec.get("recommendations", [])]
            if tag_names:
                results[sg_id] = tag_names
        except Exception:
            continue

    return results
