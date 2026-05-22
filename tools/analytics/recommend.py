"""Rule-based recommendation engine powered by Apriori association rules.

Given evidence context (tags, categories, or known tools), recommends:
  - Tools likely needed (tool recommendation)
  - Knowledge domains to search (tag recommendation)
  - Both (full-spectrum recommendation)

Scoring formula: score = confidence * lift * antecedent_match_ratio
This rewards rules where more of the user's context matches the antecedent.
"""

import os
from typing import Dict, List, Set, Tuple, Optional

from tools.analytics.apriori import (
    generate_frequent_itemsets,
    generate_association_rules,
)
from tools.analytics.transactions import extract_transactions


def _build_rule_index(
    kb_root: str,
    min_support: float = 0.1,
    min_confidence: float = 0.3,
    min_lift: float = 1.0,
) -> Tuple[List[Dict], List[Set[str]], List[str]]:
    """Build a full rule index from the knowledge base.

    Returns:
        (rules, transactions, filenames)
    """
    transactions, filenames = extract_transactions(
        kb_root, item_types=("tags", "tools", "categories")
    )
    if not transactions:
        return [], [], []

    frequent = generate_frequent_itemsets(transactions, min_support=min_support)
    if not frequent or max(frequent.keys()) < 2:
        return [], transactions, filenames

    rules = generate_association_rules(
        frequent,
        transactions=transactions,
        min_confidence=min_confidence,
        min_lift=min_lift,
    )
    return rules, transactions, filenames


def _is_tool(item: str, tools_vocab: Set[str]) -> bool:
    """Heuristic: classify item as tool vs tag/category."""
    return item in tools_vocab


def recommend(
    context: List[str],
    kb_root: Optional[str] = None,
    target: str = "tools",
    min_support: float = 0.08,
    min_confidence: float = 0.3,
    min_lift: float = 1.0,
    top_n: int = 10,
) -> Dict:
    """Recommend tools or tags based on evidence context.

    Args:
        context: List of items describing the current case (tags, evidence types,
                 categories, or tools already identified).
        kb_root: Path to knowledge/ directory. Auto-detected if None.
        target: What to recommend — 'tools', 'tags', or 'all'.
        min_support: Minimum support for rule mining.
        min_confidence: Minimum confidence for rules.
        min_lift: Minimum lift for rules.
        top_n: Max number of recommendations to return.

    Returns:
        Dict with keys:
        - context: original context items
        - target: recommendation target type
        - recommendations: list of {item, score, evidence_rules, rationale}
        - rules_checked: total rules evaluated
        - rules_matched: rules that matched the context
    """
    if kb_root is None:
        kb_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "knowledge"
        )

    context_set = set(c.lower().strip() for c in context)

    # Get separate transactions for tool vocabulary
    tools_txns, _ = extract_transactions(kb_root, item_types=("tools",))
    tools_vocab: Set[str] = set()
    for txn in tools_txns:
        tools_vocab.update(txn)

    # Mine rules from all item types combined
    rules, transactions, filenames = _build_rule_index(
        kb_root, min_support=min_support,
        min_confidence=min_confidence, min_lift=min_lift,
    )

    if not rules:
        return {
            "context": context,
            "target": target,
            "recommendations": [],
            "rules_checked": 0,
            "rules_matched": 0,
        }

    # Score each rule against the context
    scored: Dict[str, Dict] = {}  # item -> aggregated scores

    for rule in rules:
        ant_set = set(rule["antecedent"])
        cons_set = set(rule["consequent"])

        # How much of the antecedent matches the user's context?
        matched = ant_set & context_set
        if not matched:
            continue

        match_ratio = len(matched) / len(ant_set)
        base_score = rule["confidence"] * rule["lift"]

        for item in cons_set:
            if item in context_set:
                continue  # Don't recommend what user already has

            # Filter by target type
            is_tool = _is_tool(item, tools_vocab)
            if target == "tools" and not is_tool:
                continue
            if target == "tags" and is_tool:
                continue

            score = base_score * match_ratio

            if item not in scored or score > scored[item]["score"]:
                scored[item] = {
                    "item": item,
                    "score": round(score, 4),
                    "confidence": rule["confidence"],
                    "lift": rule["lift"],
                    "match_ratio": round(match_ratio, 2),
                    "best_rule": f"{', '.join(rule['antecedent'])} => {', '.join(rule['consequent'])}",
                    "rule_confidence": rule["confidence"],
                    "rule_lift": rule["lift"],
                    "rule_support": rule["support"],
                    "supporting_rules": [rule],
                }
            else:
                scored[item]["supporting_rules"].append(rule)

    # Rank by score descending
    ranked = sorted(scored.values(), key=lambda r: r["score"], reverse=True)

    # Count matched rules
    matched_rules = set()
    for r in ranked:
        for sr in r["supporting_rules"]:
            ant_key = tuple(sorted(sr["antecedent"]))
            matched_rules.add(ant_key)

    # Build rationale strings
    for rec in ranked[:top_n]:
        parts = []
        if rec["match_ratio"] >= 1.0:
            parts.append(f"完全匹配你的上下文")
        elif rec["match_ratio"] >= 0.5:
            parts.append(f"部分匹配你的上下文 ({rec['match_ratio']:.0%})")
        parts.append(f"置信度 {rec['rule_confidence']:.0%}")
        if rec["rule_lift"] >= 2.0:
            parts.append(f"强正相关 (lift={rec['rule_lift']:.1f})")
        parts.append(f"规则: {rec['best_rule']}")
        rec["rationale"] = "；".join(parts)

    return {
        "context": context,
        "target": target,
        "recommendations": ranked[:top_n],
        "rules_checked": len(rules),
        "rules_matched": len(matched_rules),
    }


def format_recommendations(result: Dict) -> str:
    """Format recommendation results as a readable markdown report."""
    lines = [
        f"## 工具推荐报告",
        f"",
        f"**上下文**: {', '.join(result['context'])}",
        f"**推荐类型**: {result['target']}",
        f"**已检查规则**: {result['rules_checked']} 条",
        f"**匹配规则**: {result['rules_matched']} 组",
        f"",
    ]

    recs = result["recommendations"]
    if not recs:
        lines.append("未找到匹配的推荐。尝试降低 min_support 或 min_confidence。")
        lines.append("")
        lines.append("建议：")
        lines.append("- 提供更多上下文标签（如 `memory_forensics, windows`）")
        lines.append("- 知识库中可能缺少相关领域的方案文件")
        return "\n".join(lines)

    lines.append(f"| # | 推荐 | 评分 | 置信度 | 提升度 | 依据规则 |")
    lines.append(f"|---|------|------|--------|--------|----------|")
    for i, rec in enumerate(recs, 1):
        lines.append(
            f"| {i} | **{rec['item']}** | {rec['score']:.2f} | "
            f"{rec['rule_confidence']:.0%} | {rec['rule_lift']:.1f} | "
            f"{rec['best_rule']} |"
        )

    lines.append("")
    lines.append("### 详细说明")
    lines.append("")
    for i, rec in enumerate(recs, 1):
        lines.append(f"**{i}. {rec['item']}** (评分: {rec['score']:.2f})")
        lines.append(f"> {rec['rationale']}")
        # Show additional supporting rules if any
        if len(rec["supporting_rules"]) > 1:
            lines.append(f"> 另有 {len(rec['supporting_rules']) - 1} 条规则也支持此推荐")
        lines.append("")

    return "\n".join(lines)
