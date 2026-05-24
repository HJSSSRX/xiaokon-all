#!/usr/bin/env python3
"""宏观综合分析报告 — Macro-Level Comprehensive Analytics Report.

整合全部6个分析维度:
  1. Apriori 关联规则挖掘
  2. FCA 形式概念分析
  3. 问题本质与不变量提取
  4. NCD 归一化压缩距离
  5. 知识传播网络
  6. 因果推断与逆向推理

Usage:
  python -X utf8 tools/analytics/macro_report.py [--kb-root PATH] [--output PATH]
  python -X utf8 tools/analytics/macro_report.py --format json
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Set, Any, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════════

def _default_kb():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "knowledge")


def _load_problems(kb_root):
    """Load all problem signatures from knowledge base."""
    from tools.analytics.transactions import extract_transactions
    from tools.analytics.invariant import ProblemSignature

    txns, filenames = extract_transactions(kb_root, item_types=("tags", "tools", "categories"))

    domain_map = {
        "crypto": "crypto", "stego_crypto": "crypto",
        "computer_forensics": "computer", "c_computer": "computer",
        "memory_forensics": "memory", "mobile_forensics": "mobile",
        "m_phone": "mobile", "network_forensics": "network",
        "n_network": "network", "binary_analysis": "binary",
        "web": "web", "server_forensics": "server",
        "cloud": "cloud", "iot": "iot",
    }
    domain_label_set = set(domain_map.keys())

    problems = []
    for i, (txn, fname) in enumerate(zip(txns, filenames)):
        txn_domain = "unknown"
        for item in txn:
            if item in domain_map:
                txn_domain = domain_map[item]
                break
        features = txn - domain_label_set
        if not features:
            continue
        problems.append(ProblemSignature(
            problem_id=fname.replace("\\", "/").replace(".md", "").replace(".yaml", ""),
            features=features,
            domain=txn_domain,
        ))

    return problems, txns


def _domain_distribution(problems):
    """Count problems per domain."""
    dist = defaultdict(int)
    for p in problems:
        dist[p.domain] += 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


def _format_stat(value, suffix="", default="N/A"):
    """Format a stat value for display."""
    if value is None:
        return default
    if isinstance(value, float):
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


# ═══════════════════════════════════════════════════════════════════════════════════
# Section 1: Apriori Association Rules
# ═══════════════════════════════════════════════════════════════════════════════════

def analyze_apriori(kb_root, txns) -> Dict[str, Any]:
    """Run Apriori association rule mining."""
    from tools.analytics.apriori import generate_frequent_itemsets, generate_association_rules

    result = {"status": "ok", "rules": [], "frequent_itemsets": {}}

    try:
        freq = generate_frequent_itemsets(txns, min_support=0.08)
        result["frequent_itemsets"] = {
            str(k): len(v) for k, v in freq.items()
        }
        total_freq = sum(len(v) for v in freq.values())
        result["total_frequent"] = total_freq

        if freq and max(freq.keys()) >= 2:
            rules = generate_association_rules(
                freq, transactions=txns,
                min_confidence=0.3, min_lift=1.2,
            )
            result["n_rules"] = len(rules)

            # Top rules by lift
            top_rules = sorted(rules, key=lambda r: r.get("lift", 0))[-20:]
            for r in top_rules:
                result["rules"].append({
                    "antecedent": list(r["antecedent"]),
                    "consequent": list(r["consequent"]),
                    "confidence": round(r["confidence"], 3),
                    "lift": round(r["lift"], 2),
                    "support": round(r["support"], 3),
                })
        else:
            result["n_rules"] = 0
            result["status"] = "insufficient_data"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Section 2: FCA Formal Concept Analysis
# ═══════════════════════════════════════════════════════════════════════════════════

def analyze_fca(kb_root, txns) -> Dict[str, Any]:
    """Run Formal Concept Analysis."""
    from tools.analytics.grouptheory import (
        FormalContext, build_lattice, compute_equivalence_classes,
        compute_implication_basis, detect_sublattice_gaps,
        detect_potential_synonyms,
    )

    result = {"status": "ok"}

    try:
        ctx = FormalContext(txns)
        result["n_transactions"] = ctx.n_transactions
        result["n_items"] = ctx.n_items

        # Lattice
        lattice = build_lattice(ctx, min_support=0.05, max_concepts=300)
        result["n_concepts"] = lattice.get("concept_count", 0)
        result["lattice_height"] = lattice.get("height", 0)
        result["lattice_edges"] = lattice.get("edge_count", 0)

        # Equivalence classes
        eq_classes = compute_equivalence_classes(ctx)
        result["n_equivalence_classes"] = len(eq_classes)
        result["n_equivalent_items"] = sum(len(c.items) for c in eq_classes)
        result["top_equivalences"] = []
        for c in eq_classes[:5]:
            result["top_equivalences"].append({
                "items": list(c.items)[:4],
                "support": round(c.support, 3),
                "interpretation": c.interpretation,
            })

        # Implication basis
        basis = compute_implication_basis(ctx, min_support=0.05)
        result["n_implications"] = len(basis)
        result["top_implications"] = []
        for imp in basis[:8]:
            result["top_implications"].append({
                "premise": list(imp.premise) if imp.premise else ["(全局)"],
                "conclusion": list(imp.conclusion),
                "support": round(imp.support, 3),
            })

        # Knowledge gaps
        gaps = detect_sublattice_gaps(ctx, max_size=4)
        result["n_gaps"] = len(gaps)
        result["n_critical_gaps"] = sum(1 for g in gaps if g.severity == "critical")
        result["top_gaps"] = []
        for g in gaps[:5]:
            interp = "所有两两组合都存在，但完整组合缺失"
            if not g.full_cooccurs and g.severity == "critical":
                interp = f"严重盲区：{g.n_items}项的组合从未一起出现"
            result["top_gaps"].append({
                "items": list(g.items),
                "severity": g.severity,
                "interpretation": interp,
            })

        # Synonyms
        synonyms = detect_potential_synonyms(ctx)
        result["n_synonyms"] = len(synonyms)
        result["top_synonyms"] = [
            {"item_a": a, "item_b": b, "similarity": round(s, 3)}
            for a, b, s in synonyms[:8]
        ]

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Section 3: Problem Essence & Invariants
# ═══════════════════════════════════════════════════════════════════════════════════

def analyze_invariants(problems) -> Dict[str, Any]:
    """Run invariant extraction and problem essence analysis."""
    from tools.analytics.invariant import (
        FeatureSpace, InvariantExtractor, build_domain_transformation_rules,
        build_transformation_group, compute_orbit_decomposition,
        detect_isomorphisms, find_analogous_problems,
    )

    result = {"status": "ok", "domains": {}, "isomorphisms": [], "analogues": []}

    try:
        rules = build_domain_transformation_rules()
        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.15, min_invariance=0.4)

        result["n_problems_analyzed"] = len(problems)
        result["n_profiles"] = len(report.profiles)
        result["n_cross_invariants"] = len(report.cross_problem_invariants)
        result["n_transform_rules"] = len(rules)

        # Per-domain summary
        domain_profiles = defaultdict(list)
        for prof in report.profiles:
            domain_profiles[prof.problem_type or "unknown"].append(prof)

        for domain, profs in sorted(domain_profiles.items()):
            n_core = sum(len(p.core_invariants) for p in profs)
            n_struct = sum(len(p.structural_invariants) for p in profs)
            n_var = sum(len(p.variable_features) for p in profs)

            # Domain essence from cross_problem_invariants
            essence_items = []
            for items in report.domain_essence[:3]:
                essence_items.extend(items)
            essence_str = ", ".join(essence_items[:5]) if essence_items else ""

            result["domains"][domain] = {
                "n_problems": len(profs),
                "avg_core_invariants": round(n_core / max(1, len(profs)), 1),
                "avg_structural_invariants": round(n_struct / max(1, len(profs)), 1),
                "avg_variable_features": round(n_var / max(1, len(profs)), 1),
                "essence_preview": essence_str[:120],
            }

        # Orbit decomposition
        space = FeatureSpace()
        for p in problems:
            for feat in sorted(p.features):
                space.add_feature(feat, p.domain)
        group = build_transformation_group(space, rules)
        decomp = compute_orbit_decomposition(space, group)
        result["n_orbits"] = len(decomp.orbits)
        result["n_trivial_orbits"] = sum(1 for o in decomp.orbits if len(o) == 1)
        result["top_orbit_sizes"] = [
            len(orbit) for orbit in sorted(decomp.orbits, key=len, reverse=True)[:10]
        ]

        # Cross-domain isomorphisms
        if report.profiles and len(report.profiles) >= 2:
            isomorphisms = detect_isomorphisms(
                report.profiles, min_score=0.25, cross_domain_only=True,
            )
            result["n_isomorphisms"] = len(isomorphisms)
            for iso in isomorphisms[:5]:
                result["isomorphisms"].append({
                    "source": iso.source_id,
                    "source_domain": iso.source_domain,
                    "target": iso.target_id,
                    "target_domain": iso.target_domain,
                    "score": round(iso.score, 3),
                    "type": iso.isomorphism_type,
                    "shared_core": iso.shared_core_count,
                })

            # Analogous problem pairs
            analogues = find_analogous_problems(
                report.profiles, min_shared_core=1,
            )
            result["n_analogues"] = len(analogues)
            for pid_a, pid_b, n_shared, shared in analogues[:5]:
                shared_strs = [", ".join(s) for s in shared[:3]]
                result["analogues"].append({
                    "problem_a": pid_a,
                    "problem_b": pid_b,
                    "shared_count": n_shared,
                    "shared_items": shared_strs,
                })
        else:
            result["n_isomorphisms"] = 0

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Section 4: NCD Normalized Compression Distance
# ═══════════════════════════════════════════════════════════════════════════════════

def analyze_ncd(problems) -> Dict[str, Any]:
    """Run NCD similarity analysis."""
    from tools.analytics.ncd import (
        ncd_matrix_from_features, ncd_hierarchical_clustering,
        flatten_clusters, detect_ncd_anomalies,
    )

    result = {"status": "ok"}

    try:
        feat_dict = {p.problem_id: sorted(p.features) for p in problems}
        if len(feat_dict) < 2:
            result["status"] = "insufficient_data"
            return result

        matrix = ncd_matrix_from_features(feat_dict)
        result["n_objects"] = matrix.n_objects
        result["n_pairs"] = matrix.n_objects * (matrix.n_objects - 1) // 2
        result["global_mean_ncd"] = round(matrix.avg_distance(), 4)
        result["min_ncd"] = round(matrix.min_distance(), 4)
        result["max_ncd"] = round(matrix.max_distance(), 4)

        # Compute std
        vals = [matrix.get_by_idx(i, j)
                for i in range(matrix.n_objects)
                for j in range(i + 1, matrix.n_objects)]
        if vals:
            mean = sum(vals) / len(vals)
            std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            result["global_std_ncd"] = round(std, 4)
        else:
            result["global_std_ncd"] = 0.0

        # Closest pairs
        closest = []
        for i in range(matrix.n_objects):
            obj_id = matrix.object_ids[i]
            nn = matrix.nearest_neighbors(obj_id, k=2)
            for nid, dist in nn[:1]:
                if dist > 0:
                    closest.append((obj_id, nid, round(dist, 4)))
        closest.sort(key=lambda x: x[2])
        result["closest_pairs"] = closest[:10]

        # Clustering
        dendrogram = ncd_hierarchical_clustering(matrix)
        clusters = flatten_clusters(dendrogram, threshold=0.5)
        result["n_clusters"] = len(clusters)
        result["cluster_sizes"] = [c.size for c in clusters]

        # Single-entity clusters
        result["n_singleton_clusters"] = sum(1 for c in clusters if c.size == 1)
        result["n_multi_clusters"] = sum(1 for c in clusters if c.size > 1)

        # Anomalies
        anomalies = detect_ncd_anomalies(matrix, z_threshold=2.0)
        result["n_anomalies"] = len(anomalies)
        result["anomalies"] = []
        for a in anomalies[:5]:
            result["anomalies"].append({
                "object_id": a["object_id"],
                "mean_ncd": round(a["mean_ncd"], 4),
                "z_score": round(a["z_score"], 2),
            })

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Section 5: Knowledge Propagation Network
# ═══════════════════════════════════════════════════════════════════════════════════

def analyze_propagation(problems) -> Dict[str, Any]:
    """Run knowledge propagation network analysis."""
    from tools.analytics.invariant import (
        FeatureSpace, InvariantExtractor, build_domain_transformation_rules,
        detect_isomorphisms, build_propagation_network, trace_knowledge_flow,
    )

    result = {"status": "ok"}

    try:
        rules = build_domain_transformation_rules()
        space = FeatureSpace()
        for p in problems:
            for feat in sorted(p.features):
                space.add_feature(feat, p.domain)

        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.15)

        if not report.profiles or len(report.profiles) < 2:
            result["status"] = "insufficient_data"
            return result

        isomorphisms = detect_isomorphisms(
            report.profiles, min_score=0.25, cross_domain_only=True,
        )
        network = build_propagation_network(
            report.profiles, isomorphisms, rules, space,
        )

        result["n_atoms"] = len(network.atoms)
        # Count edges from transitions dict
        total_edges = sum(len(edges) for edges in network.transitions.values())
        result["n_edges"] = total_edges
        result["n_domain_transitions"] = len(network.domain_transitions)

        # Domains: unique from all atoms
        all_domains = set()
        for atom in network.atoms.values():
            if atom.domain:
                all_domains.add(atom.domain)
        result["n_domains"] = len(all_domains)

        # Atoms per domain
        domain_atom_counts = defaultdict(int)
        for aid, atom in network.atoms.items():
            domain_atom_counts[atom.domain or "?"] += 1
        result["atoms_by_domain"] = dict(sorted(
            domain_atom_counts.items(), key=lambda x: -x[1]
        ))

        # Domain transitions
        result["domain_transitions"] = []
        for (src, tgt), paths in sorted(
            network.domain_transitions.items(),
            key=lambda x: -len(x[1])
        )[:8]:
            result["domain_transitions"].append({
                "source_domain": src,
                "target_domain": tgt,
                "n_paths": len(paths),
            })

        # Knowledge flow for top transitions
        result["knowledge_flows"] = []
        for (src, tgt), paths in sorted(
            network.domain_transitions.items(),
            key=lambda x: -len(x[1])
        )[:3]:
            flow = trace_knowledge_flow(src, tgt, isomorphisms, report.profiles)
            n_direct = len(flow.get("direct_flows", []))
            n_composite = len(flow.get("composite_flows", []))
            result["knowledge_flows"].append({
                "source": src,
                "target": tgt,
                "n_direct_mappings": n_direct,
                "n_composite_mappings": n_composite,
                "flow_density": round(flow.get("flow_density", 0), 3),
            })

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Section 6: Causal Inference
# ═══════════════════════════════════════════════════════════════════════════════════

def analyze_causality(kb_root, txns, problems) -> Dict[str, Any]:
    """Run causal inference analysis."""
    from tools.analytics.causality import (
        build_causal_graph_from_transactions, find_root_causes,
        causal_discovery, abductive_inference, infer_problem_domain,
    )

    result = {"status": "ok"}

    try:
        # Domain labels per transaction
        domain_map = {
            "crypto": "crypto", "stego_crypto": "crypto",
            "computer_forensics": "computer", "c_computer": "computer",
            "memory_forensics": "memory", "mobile_forensics": "mobile",
            "m_phone": "mobile", "network_forensics": "network",
            "n_network": "network", "binary_analysis": "binary",
            "web": "web", "server_forensics": "server",
            "cloud": "cloud", "iot": "iot",
        }
        domain_per_txn = {}
        for i, txn in enumerate(txns):
            for item in txn:
                if item in domain_map:
                    domain_per_txn[i] = domain_map[item]
                    break

        # Build graph
        graph = build_causal_graph_from_transactions(
            txns, domain_per_txn, min_confidence=0.3,
        )
        result["n_nodes"] = graph.n_nodes()
        result["n_edges"] = graph.n_edges()

        # Root / leaf stats
        roots = [n for n in graph.nodes if not graph.parents(n)]
        leaves = [n for n in graph.nodes if not graph.children(n)]
        result["n_root_causes"] = len(roots)
        result["n_leaf_effects"] = len(leaves)

        # Node type breakdown
        type_counts = defaultdict(int)
        for node in graph.nodes:
            type_counts[graph.node_types.get(node, "feature")] += 1
        result["node_types"] = dict(type_counts)

        # Top causal edges
        top_edges = sorted(graph.edges, key=lambda e: -e.strength)[:10]
        result["top_edges"] = []
        for e in top_edges:
            result["top_edges"].append({
                "cause": e.cause,
                "effect": e.effect,
                "strength": round(e.strength, 3),
                "type": e.edge_type,
            })

        # Edge type distribution
        etype_counts = defaultdict(int)
        for e in graph.edges:
            etype_counts[e.edge_type] += 1
        result["edge_types"] = dict(etype_counts)

        # Root cause analysis for top features
        from tools.analytics.apriori import generate_frequent_itemsets
        freq = generate_frequent_itemsets(txns, min_support=0.2)
        if 1 in freq:
            top_items = sorted(freq[1].items(), key=lambda x: -x[1])[:5]
            result["root_cause_examples"] = []
            for item, _ in top_items:
                roots_list = find_root_causes(item, graph, max_depth=3)
                if roots_list:
                    result["root_cause_examples"].append({
                        "feature": item,
                        "n_roots": len(roots_list),
                        "top_root": roots_list[0].feature,
                        "top_strength": round(roots_list[0].strength, 3),
                    })

        # Causal discovery (PC-like) for comparison
        disc_graph = causal_discovery(txns, min_dependency=0.05)
        result["discovered_n_nodes"] = disc_graph.n_nodes()
        result["discovered_n_edges"] = disc_graph.n_edges()

        # Abductive validation: pick a domain with tools, try to infer it back
        result["abductive_validation"] = []
        domain_tools = defaultdict(set)
        for i, txn in enumerate(txns):
            dom = domain_per_txn.get(i, "unknown")
            for item in txn:
                if item not in domain_map:
                    domain_tools[dom].add(item)

        for dom in ["memory", "crypto", "computer", "mobile", "network"]:
            if dom in domain_tools and len(domain_tools[dom]) >= 2:
                tools = list(domain_tools[dom])[:5]
                abr = infer_problem_domain(set(tools), graph)
                if abr:
                    top_hit = abr[0]
                    result["abductive_validation"].append({
                        "true_domain": dom,
                        "observed_tools": tools,
                        "inferred_domain": top_hit.cause,
                        "posterior": top_hit.posterior,
                        "correct": top_hit.cause == dom,
                    })

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# Report Rendering
# ═══════════════════════════════════════════════════════════════════════════════════

def render_report(results: Dict[str, Any]) -> str:
    """Render the comprehensive macro report as Markdown."""
    L = []  # lines
    a = L.append

    overview = results["overview"]
    apriori = results["apriori"]
    fca = results["fca"]
    invariant = results["invariant"]
    ncd = results["ncd"]
    propagation = results["propagation"]
    causality = results["causality"]

    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # ─── Header ───
    a("# 小空知识库 — 宏观综合分析报告")
    a("")
    a(f"**生成时间**: {now}  ")
    a(f"**数据源**: {overview['kb_root']}  ")
    a(f"**分析引擎**: Apriori + FCA + Invariant + NCD + Propagation + Causal")
    a("")
    a("---")
    a("")

    # ═══ Overview ═══
    a("## 1. 知识库概览")
    a("")
    a("| 指标 | 数值 |")
    a("|------|------|")
    a(f"| 交易（题目）总数 | {overview['n_transactions']} |")
    a(f"| 唯一特征项 | {overview['n_items']} |")
    a(f"| 平均每题特征数 | {overview['avg_txn_size']:.1f} |")
    a(f"| 领域标签覆盖率 | {overview['domain_coverage']:.0%} |")
    a("")

    a("### 领域分布")
    a("")
    a("| 领域 | 题目数 | 占比 |")
    a("|------|--------|------|")
    for domain, count in sorted(overview["domain_distribution"].items(), key=lambda x: -x[1]):
        pct = count / max(1, overview["n_transactions"]) * 100
        bar = "█" * max(1, int(pct / 5))
        a(f"| `{domain}` | {count} | {bar} {pct:.0f}% |")
    a("")

    # ─── Synthesis callout ───
    n_domains_labeled = sum(
        v for k, v in overview["domain_distribution"].items() if k != "unknown"
    )
    if overview["domain_coverage"] < 0.5:
        a(f"> ⚠ **注意**: 仅 {n_domains_labeled}/{overview['n_transactions']} 题有领域标签。")
        a("> 跨域分析（同构映射、知识传播、反事实推理）将在已标注题目上运行，未标注题目仅参与统计分析和聚类。")
        a("")

    a("---")
    a("")

    # ═══ Apriori ═══
    a("## 2. Apriori 关联规则挖掘")
    a("")
    a(f"- **频繁项集总数**: {apriori.get('total_frequent', 'N/A')}")
    a(f"- **关联规则数**: {apriori.get('n_rules', 'N/A')}")
    a("")

    if apriori.get("rules"):
        a("### Top 15 关联规则 (按 Lift 排序)")
        a("")
        a("| 前件 | 后件 | 置信度 | Lift | 支持度 |")
        a("|------|------|--------|------|--------|")
        for r in apriori["rules"][:15]:
            ant = ", ".join(r["antecedent"])
            cons = ", ".join(r["consequent"])
            a(f"| {ant} | {cons} | {r['confidence']:.2f} | {r['lift']:.1f} | {r['support']:.3f} |")
        a("")

        # Cross-domain rules
        domain_labels = {
            "crypto", "computer", "memory", "mobile", "network",
            "binary", "web", "server", "cloud", "iot",
            "c_computer", "computer_forensics", "memory_forensics",
            "mobile_forensics", "network_forensics", "binary_analysis",
            "server_forensics", "crypto", "stego_crypto", "m_phone", "n_network",
        }
        cross_domain = [
            r for r in apriori["rules"]
            if any(a in domain_labels for a in r["antecedent"])
            or any(c in domain_labels for c in r["consequent"])
        ]
        if cross_domain:
            a(f"**跨域规则**: {len(cross_domain)} 条涉及领域标签")
            a("")
    elif apriori.get("status") == "insufficient_data":
        a("> 数据不足以挖掘关联规则（需更多题目或降低最小支持度阈值）。")
        a("")

    a("---")
    a("")

    # ═══ FCA ═══
    a("## 3. 形式概念分析 (FCA)")
    a("")
    a(f"- **交易数**: {fca.get('n_transactions', 'N/A')}")
    a(f"- **唯一项**: {fca.get('n_items', 'N/A')}")
    a(f"- **概念数**: {fca.get('n_concepts', 'N/A')}")
    a(f"- **格高度**: {fca.get('lattice_height', 'N/A')}")
    a(f"- **格边数**: {fca.get('lattice_edges', 'N/A')}")
    a(f"- **等价类**: {fca.get('n_equivalence_classes', 'N/A')} (覆盖 {fca.get('n_equivalent_items', 'N/A')} 项)")
    a(f"- **蕴含规则**: {fca.get('n_implications', 'N/A')} 条")
    a(f"- **知识盲区**: {fca.get('n_gaps', 'N/A')} 个 (严重: {fca.get('n_critical_gaps', 'N/A')})")
    a(f"- **近等价项 (潜在同义词)**: {fca.get('n_synonyms', 'N/A')} 对")
    a("")

    if fca.get("top_implications"):
        a("### 逻辑蕴含规则")
        a("")
        a("| 前提 | 结论 | 支持度 |")
        a("|------|------|--------|")
        for imp in fca["top_implications"][:8]:
            prem = ", ".join(imp["premise"])
            cons = ", ".join(imp["conclusion"])
            a(f"| {prem} | {cons} | {imp['support']:.3f} |")
        a("")

    if fca.get("top_equivalences"):
        a("### 等价项群 (可互相替换)")
        a("")
        for eq in fca["top_equivalences"][:5]:
            items = ", ".join(eq["items"])
            a(f"- **{{{items}}}** (sup={eq['support']:.3f}): {eq['interpretation']}")
        a("")

    if fca.get("top_gaps"):
        a("### 知识盲区")
        a("")
        for g in fca["top_gaps"][:5]:
            items = ", ".join(g["items"])
            sev = "🔴" if g["severity"] == "critical" else "🟡"
            a(f"- {sev} **{{{items}}}** — {g['interpretation']}")
        a("")

    if fca.get("top_synonyms"):
        a("### 近等价项 (潜在冗余)")
        a("")
        for s in fca["top_synonyms"][:6]:
            a(f"- `{s['item_a']}` ≈ `{s['item_b']}` (Jaccard {s['similarity']:.3f})")
        a("")

    a("---")
    a("")

    # ═══ Invariant ═══
    a("## 4. 问题本质识别 & 不变量提取")
    a("")
    a(f"- **分析题目数**: {invariant.get('n_problems_analyzed', 'N/A')}")
    a(f"- **生成特征画像**: {invariant.get('n_profiles', 'N/A')}")
    a(f"- **变换规则数**: {invariant.get('n_transform_rules', 'N/A')}")
    a(f"- **轨道数**: {invariant.get('n_orbits', 'N/A')} (平凡轨道: {invariant.get('n_trivial_orbits', 'N/A')})")
    a(f"- **最大轨道大小**: {max(invariant.get('top_orbit_sizes', [0])) if invariant.get('top_orbit_sizes') else 'N/A'}")
    a("")

    # Domain essence table
    if invariant.get("domains"):
        a("### 各领域问题本质")
        a("")
        a("| 领域 | 题目数 | 平均核心不变量 | 平均结构不变量 | 平均可变特征 | 本质描述 |")
        a("|------|--------|----------------|----------------|--------------|----------|")
        for domain, info in sorted(invariant["domains"].items()):
            essence = info.get("essence_preview", "")[:80]
            a(f"| `{domain}` | {info['n_problems']} | {info['avg_core_invariants']} | "
              f"{info['avg_structural_invariants']} | {info['avg_variable_features']} | "
              f"{essence} |")
        a("")

    # Isomorphisms
    if invariant.get("isomorphisms"):
        a("### 跨域结构同构映射")
        a("")
        a("| 源题目 | 源域 | 目标题目 | 目标域 | 得分 | 类型 | 共享核心 |")
        a("|--------|------|----------|--------|------|------|----------|")
        for iso in invariant["isomorphisms"][:8]:
            a(f"| `{iso['source']}` | {iso['source_domain']} | `{iso['target']}` "
              f"| {iso['target_domain']} | {iso['score']:.2f} | {iso['type']} | {iso['shared_core']} |")
        a("")
    else:
        a("> 未检测到跨域同构映射（领域标签不足或分差过大）。")
        a("")

    # Analogues
    if invariant.get("analogues"):
        a("### 相似题目对")
        a("")
        for ana in invariant["analogues"][:5]:
            a(f"- **{ana['problem_a']}** ↔ **{ana['problem_b']}** "
              f"({ana['shared_count']} 共享核心: {', '.join(ana['shared_items'])})")
        a("")

    a("---")
    a("")

    # ═══ NCD ═══
    a("## 5. NCD 归一化压缩距离分析")
    a("")
    a(f"- **对象数**: {ncd.get('n_objects', 'N/A')}")
    a(f"- **全局平均距离**: {ncd.get('global_mean_ncd', 'N/A')}")
    a(f"- **全局标准差**: {ncd.get('global_std_ncd', 'N/A')}")
    a(f"- **最近距离**: {ncd.get('min_ncd', 'N/A')}")
    a(f"- **最远距离**: {ncd.get('max_ncd', 'N/A')}")
    a(f"- **簇数 (阈值0.5)**: {ncd.get('n_clusters', 'N/A')}")
    a(f"- **多实体簇**: {ncd.get('n_multi_clusters', 'N/A')}, 单例簇: {ncd.get('n_singleton_clusters', 'N/A')}")
    a(f"- **异常对象 (z>2.0)**: {ncd.get('n_anomalies', 'N/A')}")
    a("")

    if ncd.get("closest_pairs"):
        a("### 最相似题目对")
        a("")
        a("| 题目A | 题目B | NCD距离 |")
        a("|--------|--------|---------|")
        for a_id, b_id, dist in ncd["closest_pairs"][:10]:
            a(f"| `{a_id}` | `{b_id}` | {dist} |")
        a("")

    if ncd.get("anomalies"):
        a("### 异常/孤立题目")
        a("")
        a("| 题目 | 平均NCD | Z分数 |")
        a("|------|---------|-------|")
        for anom in ncd["anomalies"][:5]:
            a(f"| `{anom['object_id']}` | {anom['mean_ncd']} | {anom['z_score']:.1f} |")
        a("")

    a("---")
    a("")

    # ═══ Propagation ═══
    a("## 6. 知识传播网络")
    a("")
    a(f"- **知识原子**: {propagation.get('n_atoms', 'N/A')}")
    a(f"- **传播边**: {propagation.get('n_edges', 'N/A')}")
    a(f"- **涉及领域**: {propagation.get('n_domains', 'N/A')}")
    a(f"- **跨域传播路径**: {propagation.get('n_domain_transitions', 'N/A')}")
    a("")

    if propagation.get("atoms_by_domain"):
        a("### 各领域知识原子数")
        a("")
        for dom, count in propagation["atoms_by_domain"].items():
            a(f"- `{dom}`: {count}")
        a("")

    if propagation.get("domain_transitions"):
        a("### 知识跨域传播路径")
        a("")
        a("| 源域 | 目标域 | 传播路径数 |")
        a("|------|--------|------------|")
        for dt in propagation["domain_transitions"][:8]:
            a(f"| `{dt['source_domain']}` | `{dt['target_domain']}` | {dt['n_paths']} |")
        a("")

    a("---")
    a("")

    # ═══ Causal ═══
    a("## 7. 因果推断与逆向推理")
    a("")
    a(f"- **因果图节点**: {causality.get('n_nodes', 'N/A')}")
    a(f"- **因果图边**: {causality.get('n_edges', 'N/A')}")
    a(f"- **根因节点**: {causality.get('n_root_causes', 'N/A')}")
    a(f"- **叶效应节点**: {causality.get('n_leaf_effects', 'N/A')}")
    a("")

    if causality.get("node_types"):
        a("### 节点类型分布")
        a("")
        for ntype, count in sorted(causality["node_types"].items()):
            a(f"- `{ntype}`: {count}")
        a("")

    if causality.get("edge_types"):
        a("### 因果边类型")
        a("")
        for etype, count in sorted(causality["edge_types"].items()):
            a(f"- `{etype}`: {count}")
        a("")

    if causality.get("top_edges"):
        a("### Top 因果边 (最强因果链)")
        a("")
        a("| 原因 | 结果 | 强度 | 类型 |")
        a("|------|------|------|------|")
        for e in causality["top_edges"][:10]:
            a(f"| `{e['cause']}` | `{e['effect']}` | {e['strength']:.3f} | {e['type']} |")
        a("")

    # Abductive validation
    if causality.get("abductive_validation"):
        a("### 逆向推理验证")
        a("")
        a("| 真实领域 | 观察工具 | 推断领域 | 后验概率 | 正确? |")
        a("|----------|----------|----------|----------|-------|")
        for av in causality["abductive_validation"]:
            tools_str = ", ".join(av["observed_tools"][:3])
            if len(av["observed_tools"]) > 3:
                tools_str += f" ... +{len(av['observed_tools']) - 3}"
            check = "✓" if av["correct"] else "✗"
            a(f"| `{av['true_domain']}` | {tools_str} | `{av['inferred_domain']}` "
              f"| {av['posterior']:.3f} | {check} |")
        a("")

        correct_count = sum(1 for av in causality["abductive_validation"] if av["correct"])
        total_av = len(causality["abductive_validation"])
        a(f"**逆向推理准确率**: {correct_count}/{total_av} ({correct_count/max(1,total_av)*100:.0f}%)")
        a("")

    # Causal discovery comparison
    a(f"### PC因果发现")
    a(f"- 发现节点: {causality.get('discovered_n_nodes', 'N/A')}")
    a(f"- 发现边: {causality.get('discovered_n_edges', 'N/A')}")
    a("")

    a("---")
    a("")

    # ═══ Synthesis ═══
    a("## 8. 综合洞察与建议")
    a("")

    findings = _synthesize_findings(results)
    for i, finding in enumerate(findings, 1):
        a(f"### 8.{i} {finding['title']}")
        a("")
        a(finding["body"])
        a("")

    a("---")
    a("")
    a(f"*报告由 小空 宏观分析引擎自动生成 — {now}*")
    a("")

    return "\n".join(L)


def _synthesize_findings(results: Dict[str, Any]) -> List[Dict[str, str]]:
    """Cross-reference analysis results to produce high-level insights."""
    findings = []
    overview = results["overview"]
    apriori = results["apriori"]
    fca = results["fca"]
    invariant = results["invariant"]
    ncd = results["ncd"]
    propagation = results["propagation"]
    causality = results["causality"]

    # Finding 1: KB completeness
    n_txns = overview["n_transactions"]
    n_items = overview["n_items"]
    avg_size = overview["avg_txn_size"]
    dom_cov = overview["domain_coverage"]

    if dom_cov < 0.5:
        findings.append({
            "title": "领域标签覆盖率偏低",
            "body": (
                f"当前仅 {dom_cov:.0%} 的题目有领域标签。这意味着跨域同构映射、"
                f"知识传播网络和反事实推理等高级功能只能利用约 {int(n_txns * dom_cov)} 道题目。\n\n"
                f"**建议**: 为所有题目补充领域标签（使用 `categories: [domain_name]` 前置元数据），"
                f"以充分释放跨域分析的潜力。可先用 NCD 聚类结果辅助自动标注。"
            ),
        })

    # Finding 2: FCA implications vs Apriori rules
    n_impl = fca.get("n_implications", 0)
    n_rules = apriori.get("n_rules", 0)
    if n_impl is not None and n_rules is not None:
        if n_impl == 0 and n_rules > 0:
            findings.append({
                "title": "特征间无严格逻辑蕴含，但存在强统计关联",
                "body": (
                    f"FCA 蕴含基为空（{n_impl} 条），说明不存在\"出现 A 则必然出现 B\"的硬逻辑约束。\n"
                    f"但 Apriori 挖掘到 {n_rules} 条高置信度统计规则，说明特征共现是概率性的。\n\n"
                    f"**解读**: 知识库中取证工具的选择是灵活多样的，没有强制的固定搭配。"
                    f"这在实践中是合理的——同一类题目可以用不同工具链解决。\n\n"
                    f"**建议**: 利用 Lift > 2.0 的强关联规则作为\"推荐搭配\"，"
                    f"而非必须遵循的规则。"
                ),
            })
        elif n_impl > 0:
            findings.append({
                "title": f"存在 {n_impl} 条逻辑蕴含规则——可编码为硬约束",
                "body": (
                    f"FCA 提取到 {n_impl} 条逻辑蕴含，表明某些特征组合之间存在必然联系。\n\n"
                    f"**建议**: 将这些蕴含规则编码到协调者的解题策略中，"
                    f"作为\"若看到 X，则必须考虑 Y\"的硬性建议。"
                ),
            })

    # Finding 3: NCD anomalies
    n_anom = ncd.get("n_anomalies", 0)
    if n_anom > 0:
        anom_ids = [a["object_id"] for a in ncd.get("anomalies", [])[:3]]
        findings.append({
            "title": f"检测到 {n_anom} 个 NCD 异常/孤立题目",
            "body": (
                f"以下题目的特征组合与知识库中其他题目显著不同"
                f"（压缩距离异常偏高）：\n\n"
                + "\n".join(f"- `{aid}`" for aid in anom_ids) +
                f"\n\n**建议**: 检查这些题目是否存在以下情况："
                f"(1) 属于罕见子领域，可考虑创建独立知识簇；"
                f"(2) 特征标注不完整，需补充标签；"
                f"(3) 实为全新题型，可作为知识库扩展的先导。"
            ),
        })

    # Finding 4: Closest problem pairs (NCD)
    closest = ncd.get("closest_pairs", [])
    if closest:
        top_pair = closest[0]
        findings.append({
            "title": "最相似题目对——潜在冗余或知识复用",
            "body": (
                f"NCD 发现 `{top_pair[0]}` 和 `{top_pair[1]}` 是距离最近的题目对"
                f"（NCD = {top_pair[2]}）。\n\n"
                f"**建议**: 检查这两道题是否高度重复——若核心特征一致仅有表面差异，"
                f"可合并或标记为\"同题不同表述\"。若核心不同但工具链高度重叠，"
                f"则正好说明跨域知识复用的潜力。"
            ),
        })

    # Finding 5: Causal abduction accuracy
    av = causality.get("abductive_validation", [])
    if av:
        correct = sum(1 for a in av if a["correct"])
        total = len(av)
        accuracy = correct / max(1, total)
        findings.append({
            "title": f"逆向推理准确率: {correct}/{total} ({accuracy:.0%})",
            "body": (
                f"从观察到的工具集逆向推断所属领域，"
                f"准确率为 {accuracy:.0%}。\n\n"
                + (f"**强项**: 逆向推理能可靠地从工具选择推断问题类型，"
                   f"可用于未知题目的自动分类。\n\n"
                   f"**改进方向**: 对于推断错误的案例，补充该领域的因果边"
                   f"（P(tool | domain)）以增强逆向推理能力。"
                   if accuracy >= 0.6 else
                   f"**注意**: 准确率偏低，主要原因是领域标签稀疏导致因果图不完整。"
                   f"补齐领域标签后，逆向推理准确率有望大幅提升。")
            ),
        })

    # Finding 6: Knowledge gaps
    n_gaps = fca.get("n_gaps", 0)
    n_crit = fca.get("n_critical_gaps", 0)
    if n_crit > 0:
        findings.append({
            "title": f"{n_crit} 个严重知识盲区需要关注",
            "body": (
                f"FCA 格分析检测到 {n_crit} 个严重知识盲区——这些特征组合在理论上"
                f"可能（出现在子格中），但在当前知识库中没有任何题目覆盖。\n\n"
                f"**建议**: 优先为这些盲区创建针对性练习题，确保知识库覆盖度的完整性。"
                f"使用 `python -m tools.cli analytics group gaps` 查看详情。"
            ),
        })

    # Finding 7: Cross-domain knowledge reuse
    isos = invariant.get("n_isomorphisms", 0)
    transitions = propagation.get("n_domain_transitions", 0)
    if isos and isos > 0:
        findings.append({
            "title": f"发现 {isos} 个跨域同构——知识可跨域迁移",
            "body": (
                f"识别到 {isos} 对跨域结构同构的题目，说明存在 {transitions} 种域间知识传播路径。\n\n"
                f"**实用价值**: 解题者在一个领域掌握的技术（如 crypto 的数学分析），"
                f"可以通过同构映射迁移到另一个领域（如 binary 的反汇编分析）。\n\n"
                f"**建议**: 在新题推荐系统中，优先推荐\"同构相似\"的题目以加速跨域学习。"
                f"使用 `python -m tools.cli analytics invariant transfer --domain-a crypto --domain-b binary`"
                f" 生成具体迁移方案。"
            ),
        })
    elif isos == 0:
        findings.append({
            "title": "未检测到跨域同构——需扩充领域标注",
            "body": (
                f"当前知识库中未检测到跨域结构同构。这可能是由于：(1) 领域标签覆盖率低"
                f"（{dom_cov:.0%}），无法进行有效的跨域对比；"
                f"(2) 各领域的题型差异确实很大，缺乏共同结构模式。\n\n"
                f"**建议**: 优先为所有题目补充 `categories:` 领域标签，然后重新运行宏观分析。"
                f"即使真实跨域同构少，这一发现本身也说明知识库的领域间有明确的界限——"
                f"这对于按领域组织学习路径是有利的信息。"
            ),
        })

    return findings


# ═══════════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════════

def generate_macro_report(kb_root: str) -> Dict[str, Any]:
    """Run all 6 analyses and return the combined results dict."""
    print("Loading knowledge base...", file=sys.stderr)
    problems, txns = _load_problems(kb_root)

    overview = {
        "kb_root": kb_root,
        "n_transactions": len(txns),
        "n_items": len(set().union(*txns)) if txns else 0,
        "avg_txn_size": sum(len(t) for t in txns) / max(1, len(txns)),
        "domain_distribution": _domain_distribution(problems),
    }
    n_labeled = sum(v for k, v in overview["domain_distribution"].items() if k != "unknown")
    overview["domain_coverage"] = n_labeled / max(1, overview["n_transactions"])

    results = {"overview": overview}

    sections = [
        ("Apriori 关联规则", lambda: analyze_apriori(kb_root, txns)),
        ("FCA 形式概念分析", lambda: analyze_fca(kb_root, txns)),
        ("不变量提取", lambda: analyze_invariants(problems)),
        ("NCD 压缩距离", lambda: analyze_ncd(problems)),
        ("知识传播网络", lambda: analyze_propagation(problems)),
        ("因果推断", lambda: analyze_causality(kb_root, txns, problems)),
    ]

    for name, analyzer in sections:
        print(f"  Running {name}...", file=sys.stderr)
        start = time.time()
        try:
            result = analyzer()
        except Exception as e:
            result = {"status": "error", "error": str(e)}
        elapsed = time.time() - start
        result["_elapsed"] = round(elapsed, 2)

        key = {
            "Apriori 关联规则": "apriori",
            "FCA 形式概念分析": "fca",
            "不变量提取": "invariant",
            "NCD 压缩距离": "ncd",
            "知识传播网络": "propagation",
            "因果推断": "causality",
        }[name]
        results[key] = result
        status = result.get("status", "?")
        print(f"    ... {status} ({elapsed:.1f}s)", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="小空知识库宏观综合分析报告"
    )
    parser.add_argument("--kb-root", default=None,
                       help="Path to knowledge/ directory")
    parser.add_argument("--output", "-o", default=None,
                       help="Output file (default: knowledge/_relations/macro_report.md)")
    parser.add_argument("--format", default="markdown",
                       choices=["markdown", "json"],
                       help="Output format (default: markdown)")
    parser.add_argument("--json-output", default=None,
                       help="Also save raw JSON results to this file")
    args = parser.parse_args()

    kb_root = args.kb_root or _default_kb()

    if not os.path.isdir(kb_root):
        print(f"ERROR: Knowledge base not found at {kb_root}")
        sys.exit(1)

    results = generate_macro_report(kb_root)

    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        report = render_report(results)
        output = args.output or os.path.join(kb_root, "_relations", "macro_report.md")
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report written to: {output}", file=sys.stderr)

        # Also print to stdout
        print(report)

    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"JSON results written to: {args.json_output}", file=sys.stderr)


if __name__ == "__main__":
    main()
