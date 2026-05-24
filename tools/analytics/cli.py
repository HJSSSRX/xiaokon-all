"""CLI interface for the analytics module.

Usage:
  python -m tools.cli analytics mine [--kb-root DIR] [--type TYPE] [--min-support S] [--min-confidence C] [--min-lift L] [--top N]
  python -m tools.cli analytics report [--kb-root DIR] [--output FILE]
  python -m tools.cli analytics group <cmd> [opts]  Group-theoretic analysis (FCA, closure, equivalence, gaps, basis)
  python -m tools.cli analytics lattice <cmd> [opts]  Formal Concept Lattice construction and exploration
  python -m tools.cli analytics invariant <cmd> [opts]  Problem essence recognition (Apriori + group theory fusion)
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
from tools.analytics.grouptheory import (
    FormalContext,
    build_lattice,
    find_concept_for_items,
    compute_equivalence_classes,
    detect_potential_synonyms,
    compute_implication_basis,
    detect_sublattice_gaps,
    detect_domain_analogues,
    compare_with_apriori,
    recommend_by_closure,
    analyze_comprehensively,
    attribute_closure,
    format_lattice_summary,
    format_implication_basis,
    format_gaps,
    format_symmetry_groups,
    format_comparison,
    format_equivalence_classes,
    format_closure_result,
)
from tools.analytics.invariant import (
    FeatureSpace,
    ProblemSignature,
    PermutationGroup,
    TransformationRule,
    InvariantExtractor,
    build_domain_transformation_rules,
    build_transformation_group,
    compute_orbit_decomposition,
    compare_problem_essences,
    find_analogous_problems,
    detect_isomorphisms,
    generate_transfer_recipe,
    build_invariant_graph,
    build_propagation_network,
    find_propagation_paths,
    find_all_reachable,
    trace_knowledge_flow,
    compute_propagation_stabilizer,
    format_essence_report,
    format_invariant_profile,
    format_essence_comparison,
    format_orbit_report,
    format_isomorphism_report,
    format_transfer_recipe,
    format_isomorphism_summary_table,
    format_propagation_path,
    format_propagation_network_summary,
    format_knowledge_flow,
    format_stabilizer_analysis,
)
from tools.analytics.ncd import (
    ncd_matrix_from_features,
    ncd_matrix_from_files,
    ncd_hierarchical_clustering,
    flatten_clusters,
    get_cluster_leaves,
    compare_ncd_with_invariants,
    detect_ncd_anomalies,
    format_ncd_matrix_summary,
    format_ncd_neighbors,
    format_ncd_clusters,
    format_ncd_invariant_comparison,
    format_ncd_anomalies,
)


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


def _default_kb_root():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "knowledge"
    )


def _build_formal_context(kb_root, item_types=("tags", "tools", "categories")):
    """Build a FormalContext from the knowledge base."""
    txns, _ = extract_transactions(kb_root, item_types=item_types)
    if not txns:
        raise SystemExit("No transactions found. Is the knowledge base populated?")
    return FormalContext(txns)


# ─── Group Theory subcommands ──────────────────────────────────────────────────

def cmd_group(args):
    """Dispatch group theory sub-subcommands."""
    kb_root = args.kb_root or _default_kb_root()

    if args.group_command == "closure":
        items = [it.strip() for it in args.items.split(",") if it.strip()]
        ctx = _build_formal_context(kb_root)
        closed = attribute_closure(ctx, set(items))
        recs = recommend_by_closure(ctx, items)
        print(format_closure_result(items, closed, recs))

    elif args.group_command == "equivalents":
        ctx = _build_formal_context(kb_root)
        classes = compute_equivalence_classes(ctx)
        print(format_equivalence_classes(classes))
        synonyms = detect_potential_synonyms(ctx)
        if synonyms:
            print(f"\n### 近等价项 (Jaccard >= 0.8)")
            for a, b, sim in synonyms[:15]:
                print(f"- `{a}` ≈ `{b}` (相似度 {sim:.3f})")

    elif args.group_command == "gaps":
        ctx = _build_formal_context(kb_root)
        gaps = detect_sublattice_gaps(ctx, max_size=args.max_size)
        print(f"Context: {ctx.n_transactions} txns, {ctx.n_items} items\n")
        print(format_gaps(gaps))

    elif args.group_command == "basis":
        ctx = _build_formal_context(kb_root)
        basis = compute_implication_basis(ctx, min_support=args.min_support)
        print(f"Context: {ctx.n_transactions} txns, {ctx.n_items} items\n")
        print(format_implication_basis(basis))

    elif args.group_command == "compare":
        ctx = _build_formal_context(kb_root)
        txns, _ = extract_transactions(kb_root)
        freq = generate_frequent_itemsets(txns, min_support=args.min_support)
        freq_flat = {}
        for k_itemsets in freq.values():
            freq_flat.update(k_itemsets)
        comparison = compare_with_apriori(ctx, freq_flat, args.min_support)
        print(format_comparison(comparison))

    elif args.group_command == "analyze":
        ctx = _build_formal_context(kb_root)
        txns, _ = extract_transactions(kb_root)
        freq = generate_frequent_itemsets(txns, min_support=args.min_support)
        freq_flat = {}
        for k_itemsets in freq.values():
            freq_flat.update(k_itemsets)
        result = analyze_comprehensively(ctx, apriori_frequent=freq_flat, min_support=args.min_support)
        _print_comprehensive(result)

    else:
        print("Unknown group subcommand. Available: closure, equivalents, gaps, basis, compare, analyze")
        print("Usage: python -m tools.cli analytics group <subcommand> [options]")


def _print_comprehensive(result):
    """Print comprehensive analysis results."""
    cs = result["context_summary"]
    print(f"## 综合分析报告")
    print(f"\n### 上下文概览")
    print(f"- 交易数: {cs['n_transactions']}")
    print(f"- 唯一项: {cs['n_items']}")
    print(f"- 平均交易大小: {cs['avg_txn_size']}")

    print(f"\n### 等价类")
    print(f"- {result['n_equivalence_classes']} 个等价类, 覆盖 {result['n_equivalent_items']} 项")
    if result["equivalence_classes"]:
        for c in result["equivalence_classes"][:5]:
            members = ", ".join(c.items[:4])
            if len(c.items) > 4:
                members += f" ... (+{len(c.items) - 4})"
            print(f"  - [{members}] (sup={c.support:.3f}, {c.interpretation})")

    print(f"\n### 蕴含基")
    print(f"- {result['n_implications']} 条逻辑规则")
    if result["implication_basis"]:
        for imp in result["implication_basis"][:5]:
            prem = ", ".join(imp.premise) if imp.premise else "(全局)"
            cons = ", ".join(imp.conclusion)
            print(f"  - {prem} => {cons} (sup={imp.support:.3f})")

    print(f"\n### 知识盲区")
    print(f"- {result['n_gaps_total']} 总缺口, {result['n_critical_gaps']} 严重")
    critical = [g for g in result["knowledge_gaps"][:5] if g.severity == "critical"]
    for g in critical[:5]:
        items = ", ".join(g.items)
        print(f"  - 严重: {{{items}}}")

    print(f"\n### 概念格")
    ls = result["lattice_summary"]
    print(f"- {ls['concept_count']} 概念, 高度 {ls['height']}, {ls['edge_count']} 边")

    if "apriori_comparison" in result:
        print(f"\n### Apriori vs FCA")
        ac = result["apriori_comparison"]
        print(f"- Apriori项集: {ac['apriori_itemsets_count']}")
        print(f"- 闭概念: {ac['closed_concepts_count']}")
        print(f"- 频繁但不闭: {ac['frequent_but_not_closed']}")
        print(f"- 闭但不频繁: {ac['closed_but_not_frequent']}")

    if "symmetry_groups" in result and result.get("n_symmetry_groups", 0) > 0:
        print(f"\n### 跨域对称")
        print(f"- {result['n_symmetry_groups']} 组")
        for g in result["symmetry_groups"][:3]:
            print(f"  - {g.interpretation}: {', '.join(g.items)}")


# ─── Lattice subcommands ───────────────────────────────────────────────────────

def cmd_lattice(args):
    """Dispatch lattice sub-subcommands."""
    kb_root = args.kb_root or _default_kb_root()

    if args.lattice_command == "build":
        ctx = _build_formal_context(kb_root)
        lattice = build_lattice(ctx, min_support=args.min_support, max_concepts=args.max_concepts)
        print(f"Context: {ctx.n_transactions} txns, {ctx.n_items} items\n")
        print(format_lattice_summary(lattice))

        concepts = lattice["concepts"]
        top_n = min(args.top, len(concepts))
        if top_n > 0:
            print(f"\n### Top {top_n} 概念 (按外延大小)")
            print(f"\n| # | 外延大小 | 内涵大小 | 代表内涵项 |")
            print(f"|---|---|---|---|")
            for i, c in enumerate(sorted(concepts, key=lambda x: -len(x.extent))[:top_n], 1):
                intent_preview = ", ".join(list(c.intent)[:5])
                if len(c.intent) > 5:
                    intent_preview += " ..."
                print(f"| {i} | {len(c.extent)} | {len(c.intent)} | {intent_preview} |")

    elif args.lattice_command == "explore":
        items = [it.strip() for it in args.items.split(",") if it.strip()]
        ctx = _build_formal_context(kb_root)
        lattice = build_lattice(ctx, min_support=0.0, max_concepts=500)
        concept = find_concept_for_items(ctx, lattice, items)
        if concept:
            print(f"## 概念探索: {', '.join(items)}")
            print(f"- 外延: {len(concept.extent)} 交易")
            print(f"- 内涵: {', '.join(concept.intent)}")
            print(f"- 支持度: {concept.support:.3f}")
        else:
            closed = attribute_closure(ctx, set(items))
            print(f"未找到精确匹配概念。")
            print(f"输入项: {items}")
            print(f"闭包: {sorted(closed)}")

    elif args.lattice_command == "domains":
        ctx = _build_formal_context(kb_root)
        txns, fnames = extract_transactions(kb_root, item_types=("categories",))
        domain_labels = _infer_domain_labels(ctx, txns)
        if domain_labels:
            groups = detect_domain_analogues(ctx, domain_labels)
            print(format_symmetry_groups(groups))
        else:
            print("No domain labels found. Items need category/domain annotations.")

    else:
        print("Unknown lattice subcommand. Available: build, explore, domains")
        print("Usage: python -m tools.cli analytics lattice <subcommand> [options]")


def _infer_domain_labels(ctx, category_txns):
    """Infer domain labels for items from category transactions."""
    domains = {}
    domain_map = {
        "computer_forensics": "computer",
        "c_computer": "computer",
        "mobile_forensics": "mobile",
        "m_phone": "mobile",
        "server_forensics": "server",
        "s_server": "server",
        "network_forensics": "network",
        "n_network": "network",
        "binary_analysis": "binary",
        "web": "web",
        "crypto": "crypto",
        "stego_crypto": "crypto",
        "cloud": "cloud",
        "iot": "iot",
    }
    for txn in category_txns:
        for cat in txn:
            domain = domain_map.get(cat.lower(), None)
            if domain:
                for item in ctx.all_items:
                    cat_txns_set = {i for i in range(ctx.n_transactions) if cat in ctx.transactions[i]}
                    item_txns_set = {i for i in range(ctx.n_transactions) if item in ctx.transactions[i]}
                    if cat_txns_set and item_txns_set:
                        jaccard = len(cat_txns_set & item_txns_set) / len(cat_txns_set | item_txns_set)
                        if jaccard > 0.3 and item not in domains:
                            domains[item] = domain
    return domains


# ─── Invariant Extraction subcommands ───────────────────────────────────────────

def _load_problem_signatures(kb_root, domain=None):
    """Load problem signatures from the knowledge base."""
    from tools.analytics.transactions import extract_transactions

    txns, filenames = extract_transactions(kb_root, item_types=("tags", "tools", "categories"))

    domain_map = {
        "crypto": "crypto", "stego_crypto": "crypto",
        "computer_forensics": "computer", "c_computer": "computer",
        "memory_forensics": "memory", "mobile_forensics": "mobile",
        "network_forensics": "network", "n_network": "network",
        "binary_analysis": "binary", "web": "web",
        "server_forensics": "server", "cloud": "cloud", "iot": "iot",
    }

    problems = []
    for i, (txn, fname) in enumerate(zip(txns, filenames)):
        txn_domain = ""
        for item in txn:
            if item in domain_map:
                txn_domain = domain_map[item]
                break

        if domain and txn_domain != domain:
            continue

        domain_labels = set(domain_map.keys())
        features = txn - domain_labels

        if not features:
            continue

        problems.append(ProblemSignature(
            problem_id=fname.replace("\\", "/").replace(".md", "").replace(".yaml", ""),
            features=features,
            domain=txn_domain,
        ))

    return problems


def cmd_invariant(args):
    """Dispatch invariant extraction subcommands."""
    kb_root = args.kb_root or _default_kb_root()

    if args.invariant_command == "essence":
        problems = _load_problem_signatures(kb_root, domain=args.domain)
        if not problems:
            print(f"No problems found" + (f" in domain '{args.domain}'" if args.domain else ""))
            return

        rules = build_domain_transformation_rules()
        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(
            min_support=args.min_support,
            min_invariance=args.min_invariance,
        )
        print(format_essence_report(report))

    elif args.invariant_command == "compare":
        problems_a = _load_problem_signatures(kb_root, domain=args.domain_a)
        problems_b = _load_problem_signatures(kb_root, domain=args.domain_b)
        if not problems_a or not problems_b:
            print("Both domains must have at least one problem.")
            return

        rules = build_domain_transformation_rules()
        ext_a = InvariantExtractor(problems_a, rules=rules)
        ext_b = InvariantExtractor(problems_b, rules=rules)

        report_a = ext_a.extract_essence(min_support=args.min_support)
        report_b = ext_b.extract_essence(min_support=args.min_support)

        if report_a.profiles and report_b.profiles:
            diff = compare_problem_essences(report_a.profiles[0], report_b.profiles[0])
            print(format_essence_comparison(diff))
        else:
            print("Could not generate profiles for both domains.")

    elif args.invariant_command == "orbits":
        problems = _load_problem_signatures(kb_root, domain=args.domain)
        if not problems:
            print("No problems found.")
            return

        rules = build_domain_transformation_rules()
        space = FeatureSpace()
        for p in problems:
            for feat in sorted(p.features):
                space.add_feature(feat, p.domain)
        group = build_transformation_group(space, rules)
        decomp = compute_orbit_decomposition(space, group)
        print(format_orbit_report(decomp, space))

    elif args.invariant_command == "analogues":
        problems = _load_problem_signatures(kb_root)
        if len(problems) < 2:
            print("Need at least 2 problems to compare.")
            return

        rules = build_domain_transformation_rules()
        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence()

        analogues = find_analogous_problems(
            report.profiles, min_shared_core=args.min_shared
        )
        if analogues:
            print("## 相似题目对 (共享核心不变量)")
            print("")
            for pid_a, pid_b, n_shared, shared in analogues[:15]:
                print(f"- **{pid_a}** ↔ **{pid_b}** ({n_shared} 个共享核心)")
                for itemset in shared[:3]:
                    print(f"  - {{{', '.join(itemset)}}}")
            print("")
        else:
            print("No analogous problem pairs found.")

    elif args.invariant_command == "transform":
        all_rules = build_domain_transformation_rules()
        if args.domain:
            all_rules = [r for r in all_rules if r.domain == args.domain]
        print("## 变换规则")
        print("")
        print("| 规则名 | 描述 | 域 | 等价特征群 |")
        print("|---|---|---|---|")
        for rule in all_rules:
            feats = ", ".join(f"`{f}`" for f in rule.feature_group[:5])
            if len(rule.feature_group) > 5:
                feats += f" ... (+{len(rule.feature_group) - 5})"
            print(f"| {rule.name} | {rule.description} | {rule.domain} | {feats} |")
        print(f"\n共 {len(all_rules)} 条变换规则")

    elif args.invariant_command == "isomorph":
        problems = _load_problem_signatures(kb_root)
        if len(problems) < 2:
            print("Need at least 2 problems from different domains.")
            return

        rules = build_domain_transformation_rules()
        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.2)

        isomorphisms = detect_isomorphisms(
            report.profiles,
            min_score=args.min_score,
            cross_domain_only=not args.all_pairs,
        )
        print(format_isomorphism_report(isomorphisms))

    elif args.invariant_command == "transfer":
        problems_a = _load_problem_signatures(kb_root, domain=args.domain_a)
        problems_b = _load_problem_signatures(kb_root, domain=args.domain_b)
        if not problems_a or not problems_b:
            print("Both domains must have at least one problem.")
            return

        rules = build_domain_transformation_rules()
        ext_a = InvariantExtractor(problems_a, rules=rules)
        ext_b = InvariantExtractor(problems_b, rules=rules)

        report_a = ext_a.extract_essence(min_support=0.2)
        report_b = ext_b.extract_essence(min_support=0.2)

        if not report_a.profiles or not report_b.profiles:
            print("Could not generate profiles for both domains.")
            return

        # Find best isomorphism between the two domains
        all_profiles = report_a.profiles + report_b.profiles
        isomorphisms = detect_isomorphisms(all_profiles, min_score=args.min_score)

        # Filter to cross-domain only (between A and B)
        cross_isos = [iso for iso in isomorphisms
                     if (iso.source_domain == args.domain_a and iso.target_domain == args.domain_b) or
                        (iso.source_domain == args.domain_b and iso.target_domain == args.domain_a)]

        if not cross_isos:
            print(f"No isomorphism found between {args.domain_a} and {args.domain_b} "
                  f"above score {args.min_score}.")
            print("Try lowering --min-score or check that both domains have sufficient problems.")
            return

        # Generate transfer recipe for the best isomorphism
        best_iso = cross_isos[0]
        src_profile = next((p for p in all_profiles if p.problem_id == best_iso.source_id), None)
        tgt_profile = next((p for p in all_profiles if p.problem_id == best_iso.target_id), None)

        if src_profile and tgt_profile:
            recipe = generate_transfer_recipe(best_iso, src_profile, tgt_profile)
            print(format_transfer_recipe(recipe))
        else:
            print("Could not locate source/target profiles.")
            print(format_isomorphism_report(cross_isos[:5]))

    elif args.invariant_command == "propagate":
        problems = _load_problem_signatures(kb_root)
        if len(problems) < 2:
            print("Need at least 2 problems to build propagation network.")
            return

        rules = build_domain_transformation_rules()
        space = FeatureSpace()
        for p in problems:
            for feat in sorted(p.features):
                space.add_feature(feat, p.domain)

        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.2)

        if not report.profiles:
            print("No profiles generated.")
            return

        isomorphisms = detect_isomorphisms(
            report.profiles, min_score=0.3, cross_domain_only=True
        )
        network = build_propagation_network(
            report.profiles, isomorphisms, rules, space
        )

        # Find or list atoms
        if args.atom_id:
            paths = find_propagation_paths(
                args.atom_id, network,
                target_domain=args.target_domain,
                max_depth=args.max_depth,
            )
            if paths:
                for p in paths[:args.top]:
                    print(format_propagation_path(p, network, detail=args.verbose))
                    print("---")
                if len(paths) > args.top:
                    print(f"... {len(paths) - args.top} more paths (use --top to see more)")
            else:
                print(f"No propagation paths found from '{args.atom_id}'")
                if args.target_domain:
                    print(f"to domain '{args.target_domain}'")
        else:
            print("Available source atoms (use --atom-id to select):")
            for aid, atom in sorted(network.atoms.items()):
                print(f"  [{atom.domain}] {aid}")

    elif args.invariant_command == "reachable":
        problems = _load_problem_signatures(kb_root)
        if not args.atom_id:
            print("--atom-id is required for reachable subcommand.")
            return

        rules = build_domain_transformation_rules()
        space = FeatureSpace()
        for p in problems:
            for feat in sorted(p.features):
                space.add_feature(feat, p.domain)

        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.2)

        if not report.profiles:
            print("No profiles generated.")
            return

        isomorphisms = detect_isomorphisms(
            report.profiles, min_score=0.3, cross_domain_only=True
        )
        network = build_propagation_network(
            report.profiles, isomorphisms, rules, space
        )

        reachable = find_all_reachable(args.atom_id, network, max_depth=args.max_depth)

        if reachable:
            print(f"# 从 `{args.atom_id}` 可达的知识原子")
            print("")
            total = 0
            for depth in sorted(reachable):
                atoms_at_depth = reachable[depth]
                total += len(atoms_at_depth)
                print(f"## 距离 {depth} ({len(atoms_at_depth)} 个原子)")
                for aid in atoms_at_depth[:10]:
                    atom = network.atoms.get(aid)
                    dom = atom.domain if atom else "?"
                    content = atom.content if atom else "?"
                    print(f"  - [{dom}] `{aid}`: {content}")
                if len(atoms_at_depth) > 10:
                    print(f"  ... 另有 {len(atoms_at_depth) - 10} 个")
                print("")
            print(f"总计: {total} 个可达原子")
        else:
            print(f"No atoms reachable from '{args.atom_id}'")

        # Also show stabilizer analysis
        if args.show_stabilizer:
            result = compute_propagation_stabilizer(
                args.atom_id, network, space, rules
            )
            print("")
            print(format_stabilizer_analysis(result))

    elif args.invariant_command == "network":
        problems = _load_problem_signatures(kb_root)
        if not problems:
            print("No problems found.")
            return

        rules = build_domain_transformation_rules()
        space = FeatureSpace()
        for p in problems:
            for feat in sorted(p.features):
                space.add_feature(feat, p.domain)

        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.2)

        isomorphisms = detect_isomorphisms(
            report.profiles, min_score=0.3, cross_domain_only=True
        )
        network = build_propagation_network(
            report.profiles, isomorphisms, rules, space
        )
        print(format_propagation_network_summary(network))

        if args.show_flow and network.domain_transitions:
            print("")
            print("## 域间知识流动")
            print("")
            for (src, tgt), paths in sorted(network.domain_transitions.items()):
                flow = trace_knowledge_flow(
                    src, tgt, isomorphisms, report.profiles
                )
                print(format_knowledge_flow(flow, src, tgt))
                print("---")

    else:
        print("Unknown invariant subcommand.")
        print("Available: essence, compare, orbits, analogues, transform, isomorph, transfer, propagate, reachable, network")
        print("Usage: python -m tools.cli analytics invariant <subcommand> [options]")


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

    # Group theory subcommands
    p_group = sub.add_parser("group", help="Group theory analysis (FCA, closure, equivalence, gaps, basis)")
    group_sub = p_group.add_subparsers(dest="group_command")

    p_closure = group_sub.add_parser("closure", help="Compute Galois closure of an item set")
    p_closure.add_argument("--items", required=True,
                          help="Comma-separated items (e.g. 'e01, memory_forensics')")
    p_closure.add_argument("--kb-root", help="Path to knowledge/ directory")

    p_equiv = group_sub.add_parser("equivalents", help="Find equivalent/substitutable items")
    p_equiv.add_argument("--kb-root", help="Path to knowledge/ directory")

    p_gaps = group_sub.add_parser("gaps", help="Detect knowledge gaps")
    p_gaps.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_gaps.add_argument("--max-size", type=int, default=4,
                       help="Max itemset size to check (default: 4)")

    p_basis = group_sub.add_parser("basis", help="Compute Duquenne-Guigues implication basis")
    p_basis.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_basis.add_argument("--min-support", type=float, default=0.05,
                        help="Min support threshold (default: 0.05)")

    p_compare = group_sub.add_parser("compare", help="Compare Apriori rules with formal concepts")
    p_compare.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_compare.add_argument("--min-support", type=float, default=0.1,
                          help="Min support threshold (default: 0.1)")

    p_analyze = group_sub.add_parser("analyze", help="Comprehensive structural analysis")
    p_analyze.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_analyze.add_argument("--min-support", type=float, default=0.05,
                          help="Min support threshold (default: 0.05)")

    # Lattice subcommands
    p_lattice = sub.add_parser("lattice", help="Formal Concept Lattice construction and exploration")
    lattice_sub = p_lattice.add_subparsers(dest="lattice_command")

    p_build = lattice_sub.add_parser("build", help="Build and summarize the concept lattice")
    p_build.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_build.add_argument("--min-support", type=float, default=0.05,
                        help="Min support threshold (default: 0.05)")
    p_build.add_argument("--top", type=int, default=10,
                        help="Number of top concepts to show (default: 10)")
    p_build.add_argument("--max-concepts", type=int, default=500,
                        help="Max concepts to enumerate (default: 500)")

    p_explore = lattice_sub.add_parser("explore", help="Explore concepts containing given items")
    p_explore.add_argument("--items", required=True,
                          help="Comma-separated items to explore")
    p_explore.add_argument("--kb-root", help="Path to knowledge/ directory")

    p_domains = lattice_sub.add_parser("domains", help="Cross-domain symmetry analysis")
    p_domains.add_argument("--kb-root", help="Path to knowledge/ directory")

    # Invariant extraction subcommands
    p_invariant = sub.add_parser("invariant", help="Problem essence recognition (Apriori + group theory fusion)")
    inv_sub = p_invariant.add_subparsers(dest="invariant_command")

    p_essence = inv_sub.add_parser("essence", help="Extract problem essence for a domain")
    p_essence.add_argument("--domain", default=None,
                          help="Filter problems by domain (e.g. crypto, memory_forensics)")
    p_essence.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_essence.add_argument("--min-support", type=float, default=0.3,
                          help="Min support for Apriori (default: 0.3)")
    p_essence.add_argument("--min-invariance", type=float, default=0.5,
                          help="Min invariance threshold (default: 0.5)")

    p_inv_compare = inv_sub.add_parser("compare", help="Compare invariant profiles of two problem types")
    p_inv_compare.add_argument("--domain-a", required=True, help="First domain to compare")
    p_inv_compare.add_argument("--domain-b", required=True, help="Second domain to compare")
    p_inv_compare.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_inv_compare.add_argument("--min-support", type=float, default=0.3)

    p_orbits = inv_sub.add_parser("orbits", help="Show orbit decomposition of feature space")
    p_orbits.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_orbits.add_argument("--domain", default=None, help="Filter by domain")

    p_analogues = inv_sub.add_parser("analogues", help="Find analogous problem pairs")
    p_analogues.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_analogues.add_argument("--min-shared", type=int, default=2,
                            help="Min shared core invariants to report (default: 2)")

    p_transform = inv_sub.add_parser("transform", help="Show transformation rules")
    p_transform.add_argument("--domain", default=None, help="Filter rules by domain")

    p_isomorph = inv_sub.add_parser("isomorph", help="Detect cross-domain isomorphisms")
    p_isomorph.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_isomorph.add_argument("--min-score", type=float, default=0.4,
                           help="Min isomorphism score (default: 0.4)")
    p_isomorph.add_argument("--all", dest="all_pairs", action="store_true",
                           help="Include same-domain comparisons")

    p_transfer = inv_sub.add_parser("transfer", help="Generate cross-domain knowledge transfer recipe")
    p_transfer.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_transfer.add_argument("--domain-a", required=True, help="Source domain")
    p_transfer.add_argument("--domain-b", required=True, help="Target domain")
    p_transfer.add_argument("--min-score", type=float, default=0.4,
                           help="Min isomorphism score for transfer (default: 0.4)")

    p_propagate = inv_sub.add_parser("propagate", help="Find knowledge propagation paths via group action")
    p_propagate.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_propagate.add_argument("--atom-id", default=None,
                            help="Source knowledge atom ID (omit to list available atoms)")
    p_propagate.add_argument("--target-domain", default=None,
                            help="Target domain to find paths to")
    p_propagate.add_argument("--max-depth", type=int, default=6,
                            help="Max propagation depth (default: 6)")
    p_propagate.add_argument("--top", type=int, default=5,
                            help="Number of best paths to show (default: 5)")
    p_propagate.add_argument("--verbose", action="store_true",
                            help="Show detailed step descriptions")

    p_reachable = inv_sub.add_parser("reachable", help="Find all knowledge reachable from an atom")
    p_reachable.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_reachable.add_argument("--atom-id", required=True,
                            help="Source knowledge atom ID")
    p_reachable.add_argument("--max-depth", type=int, default=4,
                            help="Max reachability depth (default: 4)")
    p_reachable.add_argument("--show-stabilizer", action="store_true",
                            help="Also show stabilizer analysis for the source atom")

    p_network = inv_sub.add_parser("network", help="Display full knowledge propagation network")
    p_network.add_argument("--kb-root", help="Path to knowledge/ directory")
    p_network.add_argument("--show-flow", action="store_true",
                           help="Also show inter-domain knowledge flow analysis")

    args = parser.parse_args()

    if args.command == "mine":
        cmd_mine(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "recommend":
        cmd_recommend(args)
    elif args.command == "group":
        cmd_group(args)
    elif args.command == "lattice":
        cmd_lattice(args)
    elif args.command == "invariant":
        cmd_invariant(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
