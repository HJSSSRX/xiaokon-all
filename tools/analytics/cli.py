"""CLI interface for the analytics module.

Usage:
  python -m tools.cli analytics mine [--kb-root DIR] [--type TYPE] [--min-support S] [--min-confidence C] [--min-lift L] [--top N]
  python -m tools.cli analytics report [--kb-root DIR] [--output FILE]
"""

import argparse
import os
import sys

from tools.analytics.apriori import (
    generate_frequent_itemsets,
    generate_association_rules,
    format_rules_table,
)
from tools.analytics.transactions import extract_transactions
from tools.analytics.recommend import recommend, format_recommendations


def cmd_mine(args):
    """Mine association rules from the knowledge base."""
    kb_root = args.kb_root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "knowledge"
    )

    item_types_map = {
        "tags": ("tags",),
        "tools": ("tools",),
        "categories": ("categories",),
        "all": ("tags", "tools", "categories"),
    }
    item_types = item_types_map.get(args.type, ("tags", "tools"))

    print(f"Extracting transactions from: {kb_root}")
    print(f"Item types: {', '.join(item_types)}")
    print(f"Min support: {args.min_support}, Min confidence: {args.min_confidence}, Min lift: {args.min_lift}")

    transactions, filenames = extract_transactions(kb_root, item_types=item_types)

    if not transactions:
        print("No transactions found. Is the knowledge base populated?")
        return

    print(f"\nLoaded {len(transactions)} transactions (knowledge base files with frontmatter).")
    all_items = set()
    for txn in transactions:
        all_items.update(txn)
    print(f"Unique items: {len(all_items)}")

    # Frequent itemsets
    frequent = generate_frequent_itemsets(
        transactions, min_support=args.min_support
    )

    total_freq = sum(len(v) for v in frequent.values())
    print(f"\nFrequent itemsets found: {total_freq}")
    for k, itemsets in frequent.items():
        print(f"  k={k}: {len(itemsets)} itemsets")
        if k <= 2 and itemsets:
            for itemset, sup in list(itemsets.items())[:10]:
                print(f"    {', '.join(itemset)} (support={sup:.3f})")

    if not frequent or max(frequent.keys()) < 2:
        print("\nNo itemsets of size >= 2. Try lowering min_support.")
        return

    # Association rules
    rules = generate_association_rules(
        frequent,
        transactions=transactions,
        min_confidence=args.min_confidence,
        min_lift=args.min_lift,
    )

    print(f"\nAssociation rules found: {len(rules)}")
    top_n = min(args.top, len(rules))
    if top_n > 0:
        print(f"\nTop {top_n} rules by lift:")
        print(format_rules_table(rules, top_n=top_n))

        print("\n--- Detailed rules ---")
        for i, r in enumerate(rules[:top_n]):
            ant = ", ".join(r["antecedent"])
            cons = ", ".join(r["consequent"])
            print(
                f"\n  Rule {i+1}: {{{ant}}} => {{{cons}}}"
                f"\n    Support: {r['support']:.3f} ({r['count_both']} files)"
                f"\n    Confidence: {r['confidence']:.3f} — when {ant} appears, {cons} appears {r['confidence']*100:.0f}% of the time"
                f"\n    Lift: {r['lift']:.2f} — {'strong positive' if r['lift'] > 2 else 'positive' if r['lift'] > 1 else 'negative'} correlation"
            )

    # Print all items sorted by frequency for reference
    item_freq = {}
    for txn in transactions:
        for item in txn:
            item_freq[item] = item_freq.get(item, 0) + 1
    print(f"\n--- Item frequency (top 30) ---")
    for item, count in sorted(item_freq.items(), key=lambda x: x[1], reverse=True)[:30]:
        print(f"  {item}: {count} ({count/len(transactions)*100:.0f}%)")


def cmd_report(args):
    """Generate a full association rule report."""
    kb_root = args.kb_root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "knowledge"
    )

    output = args.output
    if not output:
        output = os.path.join(kb_root, "_relations", "association_rules.md")

    transactions, filenames = extract_transactions(kb_root)

    if not transactions:
        print("No transactions found.")
        return

    # Run with multiple parameter sets for a comprehensive report
    configs = [
        ("Tool co-occurrence", ("tools",), 0.2, 0.5, 1.0),
        ("Tag associations", ("tags",), 0.15, 0.5, 1.0),
        ("Cross-type patterns (all)", ("tags", "tools", "categories"), 0.1, 0.4, 1.0),
    ]

    lines = [
        "# Association Rule Mining Report",
        f"\nGenerated from {len(transactions)} knowledge base files.",
        "",
    ]

    for title, item_types, min_sup, min_conf, min_lift in configs:
        txns, _ = extract_transactions(kb_root, item_types=item_types)
        if not txns:
            continue
        freq = generate_frequent_itemsets(txns, min_support=min_sup)
        if not freq or max(freq.keys()) < 2:
            lines.append(f"\n## {title}\n\nNo rules found (need k>=2 itemsets).")
            continue
        rules = generate_association_rules(
            freq, transactions=txns,
            min_confidence=min_conf, min_lift=min_lift,
        )
        lines.append(f"\n## {title}")
        lines.append(f"\nParameters: min_support={min_sup}, min_confidence={min_conf}")
        lines.append(f"\nRules found: {len(rules)}")
        if rules:
            lines.append("")
            lines.append(format_rules_table(rules, top_n=30))
            # Top 5 detailed
            lines.append("\n### Top Insights\n")
            for r in rules[:5]:
                ant = ", ".join(r["antecedent"])
                cons = ", ".join(r["consequent"])
                lines.append(
                    f"- **{{{ant}}} => {{{cons}}}**: "
                    f"confidence={r['confidence']:.0%}, lift={r['lift']:.2f}. "
                    f"When you see {ant}, expect {cons}."
                )
        lines.append("")

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Report written to: {output}")


def cmd_recommend(args):
    """Recommend tools/tags based on evidence context."""
    kb_root = args.kb_root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "knowledge"
    )

    context = [c.strip() for c in args.for_context.split(",") if c.strip()]
    if not context:
        print("ERROR: --for 参数不能为空。示例: --for 'memory_forensics, windows, e01'")
        return

    result = recommend(
        context,
        kb_root=kb_root,
        target=args.target,
        min_support=args.min_support,
        min_confidence=args.min_confidence,
        min_lift=args.min_lift,
        top_n=args.top,
    )

    print(format_recommendations(result))


def main():
    parser = argparse.ArgumentParser(
        prog="forensic analytics",
        description="Association rule mining for the AutoForensicAI knowledge base",
    )
    sub = parser.add_subparsers(dest="command")

    p_mine = sub.add_parser("mine", help="Mine association rules")
    p_mine.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_mine.add_argument("--type", default="tools",
                        choices=["tags", "tools", "categories", "all"],
                        help="Item type to mine (default: tools)")
    p_mine.add_argument("--min-support", type=float, default=0.15,
                        help="Min support threshold (default: 0.15)")
    p_mine.add_argument("--min-confidence", type=float, default=0.4,
                        help="Min confidence threshold (default: 0.4)")
    p_mine.add_argument("--min-lift", type=float, default=1.0,
                        help="Min lift threshold (default: 1.0)")
    p_mine.add_argument("--top", type=int, default=15,
                        help="Number of top rules to display (default: 15)")

    p_report = sub.add_parser("report", help="Generate full association rule report")
    p_report.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_report.add_argument("--output", help="Output file path")

    p_rec = sub.add_parser("recommend", help="Recommend tools/tags for a given context")
    p_rec.add_argument("--for", dest="for_context", required=True,
                       help="Comma-separated context items (e.g. 'memory_forensics, windows, e01')")
    p_rec.add_argument("--target", default="tools",
                       choices=["tools", "tags", "all"],
                       help="What to recommend (default: tools)")
    p_rec.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_rec.add_argument("--min-support", type=float, default=0.08,
                       help="Min support threshold (default: 0.08)")
    p_rec.add_argument("--min-confidence", type=float, default=0.3,
                       help="Min confidence threshold (default: 0.3)")
    p_rec.add_argument("--min-lift", type=float, default=1.0,
                       help="Min lift threshold (default: 1.0)")
    p_rec.add_argument("--top", type=int, default=10,
                       help="Number of recommendations (default: 10)")

    args = parser.parse_args()

    if args.command == "mine":
        cmd_mine(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "recommend":
        cmd_recommend(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
