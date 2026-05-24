"""FCA Concept Lattice Analysis — 形式概念分析 / 概念格构造."""
import sys; sys.path.insert(0, ".")
from collections import defaultdict
import os

from tools.analytics.transactions import extract_transactions
from tools.analytics.grouptheory import (
    FormalContext, enumerate_concepts, build_lattice,
    compute_implication_basis, detect_sublattice_gaps,
    format_lattice_summary, format_implication_basis, format_gaps,
)

KB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                  "knowledge")

print("# FCA 形式概念格分析 (Formal Concept Analysis)")
print()
print("核心概念:")
print("- **形式语境** K = (G, M, I): G=题目(对象), M=标签/工具(属性), I=题目是否具有该属性")
print("- **Galois连接** (·)': 对象集→共享属性, 属性集→共有对象")
print("- **形式概念** (A, B): A'=B 且 B'=A (最大矩形)")
print("- **概念格**: 按概念包含关系偏序排列的完整概念集合")
print()

for item_type in ["tags", "tools"]:
    txns, _fnames = extract_transactions(KB, item_types=(item_type,))
    if not txns:
        continue

    ctx = FormalContext(transactions=txns)

    print(f"## 项类型: {item_type}")
    print(f"|G| = {ctx.n_transactions} (对象/题目数)")
    print(f"|M| = {ctx.n_items} (属性/项目数)")
    print()

    # Enumerate concepts (raw list)
    concepts = enumerate_concepts(ctx, min_support=2)
    print(f"形式概念数 (support>=2): {len(concepts)}")

    # Build lattice (dict with metadata)
    lattice = build_lattice(ctx, min_support=3)
    print(f"概念格节点数 (support>=3): {lattice['concept_count']}")
    if 'height' in lattice:
        print(f"格高度: {lattice['height']}")
    if 'top_concept_idx' in lattice:
        top_c = lattice['concepts'][lattice['top_concept_idx']]
        print(f"顶层概念(⊤): intent={{{', '.join(top_c.intent[:5])}}}"
              f"{' ...' if len(top_c.intent) > 5 else ''}")
    if 'bottom_concept_idx' in lattice:
        bot_c = lattice['concepts'][lattice['bottom_concept_idx']]
        print(f"底层概念(⊥): |extent|={len(bot_c.extent)}")
    print()

    # Lattice summary
    print(format_lattice_summary(lattice))
    print()

    # Top concepts
    if concepts:
        print("### 顶层概念 (最一般 — 覆盖最多对象)")
        topc = sorted(concepts, key=lambda c: (-len(c.extent), len(c.intent)))[:10]
        for c in topc:
            int_items = ", ".join(c.intent[:6])
            if len(c.intent) > 6:
                int_items += f" ... +{len(c.intent)-6}"
            print(f"  [{len(c.extent)} obj, {len(c.intent)} attr] intent = {{{int_items}}}")
        print()

    # Bottom concepts
    if concepts:
        print("### 底层概念 (最具体 — 属性最多)")
        botc = sorted(concepts, key=lambda c: (-len(c.intent), len(c.extent)))[:8]
        for c in botc:
            int_items = ", ".join(c.intent[:8])
            if len(c.intent) > 8:
                int_items += f" ... +{len(c.intent)-8}"
            print(f"  [{len(c.extent)} obj, {len(c.intent)} attr]")
            print(f"    intent = {{{int_items}}}")
        print()

    # Implication basis
    if len(txns) <= 200 and ctx.n_items <= 300:
        basis = compute_implication_basis(ctx, min_support=2)
        print(f"### 蕴含基 (Duquenne-Guigues Basis): {len(basis)} 条")
        if basis:
            print(format_implication_basis(basis[:20]))
        print()

    # Gaps
    gaps = detect_sublattice_gaps(ctx, max_size=4)
    if gaps:
        print(f"### 知识缺口: {len(gaps)} 个")
        print(format_gaps(gaps[:15]))
        print()

    print("---")
    print()

# ── Cross-domain ──
print("## 跨域概念格规模对比")
print()

txns_tools, fnames_tools = extract_transactions(KB, item_types=("tools",))
ctx_by_domain = defaultdict(list)
for fname, txn_items in zip(fnames_tools, txns_tools):
    parts = fname.replace("\\", "/").split("/")
    sub = parts[1] if len(parts) > 2 else parts[0]
    ctx_by_domain[sub].append(txn_items)

print("| 域 | |G| | |M| | 概念数 | 格节点 | 格高度 |")
print("|---|---|---|---|---|---|")
for domain, dom_txns in sorted(ctx_by_domain.items()):
    if len(dom_txns) < 2:
        continue
    dom_ctx = FormalContext(transactions=dom_txns)
    conc = enumerate_concepts(dom_ctx, min_support=1)
    latt = build_lattice(dom_ctx, min_support=1)
    h = latt.get('height', '?')
    print(f"| {domain} | {dom_ctx.n_transactions} | {dom_ctx.n_items} "
          f"| {len(conc)} | {latt['concept_count']} | {h} |")

print()
print("> **解读**: 格高度反映知识的层次性 — 高格表示有丰富的概念包容关系")
print("> **蕴含基**: 所有属性间逻辑蕴涵关系的极小完备集 — 知识体系的最小公理集")
print("> **知识缺口**: 在格中缺失的概念节点 — 组合搭配尚未被任何题目覆盖")
