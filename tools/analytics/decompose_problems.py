"""题目本质分解列 — Problem Essence Decomposition Table.

Runs invariant extraction (Apriori + group theory fusion) on the knowledge
base, then displays each problem broken into its core, structural, and
variable components — organized by domain.
"""
import sys
from collections import defaultdict
from tools.analytics.cli import _load_problem_signatures, _default_kb_root
from tools.analytics.invariant import (
    FeatureSpace, InvariantExtractor,
    build_domain_transformation_rules,
    build_transformation_group,
    compute_orbit_decomposition,
)

kb = _default_kb_root()
problems = _load_problem_signatures(kb)

# Split by domain
by_domain = defaultdict(list)
for p in problems:
    dom = p.domain if p.domain else "(未分类)"
    by_domain[dom].append(p)

rules = build_domain_transformation_rules()

print("# 题目本质分解列 (Problem Essence Decomposition)")
print()
print(f"题目总数: {len(problems)} | 域数: {len(by_domain)}")
print()

for domain, probs in sorted(by_domain.items()):
    print(f"## 域: {domain} ({len(probs)} 题)")
    print()

    # Build feature space for this domain
    space = FeatureSpace()
    for p in probs:
        for f in sorted(p.features):
            space.add_feature(f, domain)

    # Run invariant extraction with adjusted thresholds
    extractor = InvariantExtractor(probs, rules=rules)
    min_sup = 0.3 if len(probs) >= 3 else 0.1
    min_inv = 0.4 if len(probs) >= 3 else 0.3
    try:
        report = extractor.extract_essence(min_support=min_sup, min_invariance=min_inv)
    except Exception as e:
        print(f"  (提取失败: {e})")
        print()
        continue

    # Orbit decomposition
    group = build_transformation_group(space, rules)
    decomp = compute_orbit_decomposition(space, group)

    # ── Domain Essence ──
    if report.domain_essence:
        print("### 域本质 (跨题目核心不变量)")
        print()
        for itemset in report.domain_essence[:10]:
            items = ", ".join(sorted(itemset))
            print(f"  - {{{items}}}")
        print()

    # ── Per-Problem Decomposition ──
    print("### 逐题分解")
    print()
    for profile in report.profiles:
        pid = profile.problem_id
        # Trim long IDs
        if len(pid) > 72:
            pid = "..." + pid[-69:]

        n_core = len(profile.core_invariants)
        n_struct = len(profile.structural_invariants)
        n_var = len(profile.variable_features)

        print(f"#### {pid}")
        print(f"  (core={n_core}, structural={n_struct}, variable={n_var})")
        print()

        if profile.core_invariants:
            print("  | 层级 | 不变量 |")
            print("  |------|--------|")
            for itemset in profile.core_invariants[:6]:
                label = ", ".join(sorted(itemset))
                print(f"  | **核心** | {{{label}}} |")
            for itemset in profile.structural_invariants[:6]:
                label = ", ".join(sorted(itemset))
                print(f"  | **结构** | {{{label}}} |")
            if profile.variable_features:
                label = ", ".join(sorted(profile.variable_features[:8]))
                if len(profile.variable_features) > 8:
                    label += f" ... +{len(profile.variable_features) - 8}"
                print(f"  | **可变** | {label} |")
            print()
        else:
            print("  (无核心不变量)\n")

    # ── Orbit Summary ──
    nontriv = [o for o in decomp.orbits if len(o) > 1]
    if nontriv:
        print("### 特征轨道 (等价变换群)")
        print()
        print("  | 轨道# | 等价特征 |")
        print("  |-------|----------|")
        for oid, orbit in enumerate(decomp.orbits):
            if len(orbit) > 1:
                feats = [space.features[i] for i in sorted(orbit)]
                label = ", ".join(f"`{f}`" for f in feats[:6])
                if len(feats) > 6:
                    label += f" ... +{len(feats) - 6}"
                print(f"  | {oid} | {label} |")
        print()

    # ── Cross-Problem Invariants ──
    if report.cross_problem_invariants:
        print("### 跨题目共享不变量")
        print()
        for itemset in report.cross_problem_invariants[:8]:
            items = ", ".join(sorted(itemset))
            print(f"  - {{{items}}}")
        print()

    # ── Transformation Rules Used ──
    domain_rules = [r for r in rules if r.domain == domain or not r.domain]
    active_rules = [r for r in domain_rules
                    if any(f in space for f in r.feature_group)]
    if active_rules:
        print("### 适用变换规则")
        print()
        for r in active_rules[:8]:
            feats = ", ".join(f"`{f}`" for f in r.feature_group[:4])
            if len(r.feature_group) > 4:
                feats += f" ... +{len(r.feature_group) - 4}"
            print(f"  - **{r.name}**: {r.description} → {feats}")
        print()

    print("---")
    print()

print()
print("> 生成方式: Apriori 频繁项集挖掘 + 置换群轨道分解融合")
print("> 核心不变量: invariance >= 0.9 且 support >= 2x min_support")
print("> 结构不变量: invariance >= min_invariance")
print("> 可变特征: 低不变性特征")
