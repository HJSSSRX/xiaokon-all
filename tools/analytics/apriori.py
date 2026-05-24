"""Apriori algorithm — frequent itemset mining and association rule generation.

Pure Python implementation. No third-party ML/datamining libraries required.

Algorithm overview:
  1. Find frequent 1-itemsets (support >= min_support)
  2. Generate candidate k-itemsets by joining frequent (k-1)-itemsets
  3. Prune candidates with infrequent subsets (downward closure)
  4. Count support for remaining candidates
  5. Repeat until no more frequent itemsets found
  6. Generate association rules from frequent itemsets (confidence >= min_confidence)
"""

from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Set, Tuple, Optional


def _count_itemsets(
    transactions: List[Set[str]], candidates: List[Tuple[str, ...]]
) -> Dict[Tuple[str, ...], int]:
    """Count support for each candidate itemset across all transactions."""
    counts = defaultdict(int)
    for txn in transactions:
        for cand in candidates:
            if all(item in txn for item in cand):
                counts[cand] += 1
    return dict(counts)


def _generate_candidates(
    frequent_prev: List[Tuple[str, ...]], k: int
) -> List[Tuple[str, ...]]:
    """Generate k-sized candidates by joining (k-1)-sized frequent itemsets.

    Uses the Apriori-gen join step: two (k-1)-itemsets are joined if they share
    their first k-2 items.
    """
    candidates = set()
    n = len(frequent_prev)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = frequent_prev[i], frequent_prev[j]
            # Join if first k-2 items match
            if a[: k - 2] == b[: k - 2] and a[k - 2] < b[k - 2]:
                cand = tuple(sorted(set(a) | set(b)))
                if len(cand) == k:
                    # Prune: all (k-1)-subsets must be frequent
                    if all(
                        tuple(sorted(subset)) in frequent_prev
                        for subset in combinations(cand, k - 1)
                    ):
                        candidates.add(cand)
    return [tuple(sorted(c)) for c in candidates]


def generate_frequent_itemsets(
    transactions: List[Set[str]],
    min_support: float = 0.3,
    max_k: int = 5,
) -> Dict[int, Dict[Tuple[str, ...], float]]:
    """Find all frequent itemsets using the Apriori algorithm.

    Args:
        transactions: List of transaction sets. Each set contains item names.
        min_support: Minimum support threshold. If >= 1, treated as absolute
                     count; if < 1, treated as fraction of total transactions.
        max_k: Maximum itemset size to explore.

    Returns:
        Dict keyed by k (itemset size), each value is a dict of
        {itemset_tuple: support_fraction}.
        Returns empty dict if no frequent itemsets found.
    """
    n_txns = len(transactions)
    if n_txns == 0:
        return {}

    # Normalize min_support to absolute count
    min_count = min_support if min_support >= 1 else int(min_support * n_txns)
    if min_count < 1:
        min_count = 1

    # Collect all unique items
    all_items: Set[str] = set()
    for txn in transactions:
        all_items.update(txn)

    # Find frequent 1-itemsets
    frequent: Dict[int, Dict[Tuple[str, ...], float]] = {}
    freq_1: Dict[Tuple[str, ...], float] = {}
    for item in sorted(all_items):
        count = sum(1 for txn in transactions if item in txn)
        if count >= min_count:
            freq_1[(item,)] = count / n_txns

    if not freq_1:
        return {}

    frequent[1] = freq_1

    # Iteratively find larger frequent itemsets
    prev_frequent = list(freq_1.keys())
    k = 2
    while prev_frequent and k <= max_k:
        candidates = _generate_candidates(prev_frequent, k)
        if not candidates:
            break

        counts = _count_itemsets(transactions, candidates)
        freq_k: Dict[Tuple[str, ...], float] = {}
        for itemset, count in counts.items():
            if count >= min_count:
                freq_k[itemset] = count / n_txns

        if freq_k:
            frequent[k] = dict(
                sorted(freq_k.items(), key=lambda x: x[1], reverse=True)
            )
            prev_frequent = list(freq_k.keys())
        else:
            prev_frequent = []
        k += 1

    return frequent


def generate_association_rules(
    frequent_itemsets: Dict[int, Dict[Tuple[str, ...], float]],
    transactions: Optional[List[Set[str]]] = None,
    min_confidence: float = 0.6,
    min_lift: float = 1.0,
) -> List[Dict]:
    """Generate association rules from frequent itemsets.

    Args:
        frequent_itemsets: Output from generate_frequent_itemsets().
        transactions: Original transactions (needed for lift calculation).
                      If None, lift defaults to 1.0.
        min_confidence: Minimum confidence threshold (0.0 to 1.0).
        min_lift: Minimum lift threshold. lift=1 means independence,
                  >1 means positive correlation, <1 means negative.

    Returns:
        List of rule dicts sorted by lift descending, each containing:
        {antecedent, consequent, support, confidence, lift, count_antecedent,
         count_consequent, count_both}
    """
    n_txns = len(transactions) if transactions else 0
    rules = []

    # Pre-compute single-item support counts for lift calculation
    item_counts: Dict[str, int] = {}
    if transactions and n_txns > 0:
        for txn in transactions:
            for item in txn:
                item_counts[item] = item_counts.get(item, 0) + 1

    for k, itemsets in frequent_itemsets.items():
        if k < 2:
            continue
        for itemset, support in itemsets.items():
            itemset_set = set(itemset)
            # Generate all antecedent -> consequent splits
            for size in range(1, len(itemset)):
                for ant_indices in combinations(range(len(itemset)), size):
                    ant = tuple(itemset[i] for i in ant_indices)
                    cons = tuple(
                        itemset[i] for i in range(len(itemset)) if i not in ant_indices
                    )

                    # Confidence = P(cons | ant) = support(both) / support(ant)
                    ant_support = frequent_itemsets.get(len(ant), {}).get(ant)
                    if ant_support is None or ant_support == 0:
                        continue

                    confidence = support / ant_support
                    if confidence < min_confidence:
                        continue

                    # Lift = P(cons | ant) / P(cons) = confidence / support(consequent)
                    lift = 1.0
                    if transactions and n_txns > 0:
                        sup_cons = (
                            sum(
                                1
                                for txn in transactions
                                if all(item in txn for item in cons)
                            )
                            / n_txns
                        )
                        lift = confidence / sup_cons if sup_cons > 0 else float("inf")

                    if lift < min_lift:
                        continue

                    count_ant = int(ant_support * n_txns) if n_txns else 0
                    count_cons = (
                        item_counts.get(cons[0], 0)
                        if len(cons) == 1 and item_counts
                        else 0
                    )
                    count_both = int(support * n_txns) if n_txns else 0

                    rules.append(
                        {
                            "antecedent": ant,
                            "consequent": cons,
                            "support": round(support, 4),
                            "confidence": round(confidence, 4),
                            "lift": round(lift, 4),
                            "count_antecedent": count_ant,
                            "count_consequent": count_cons,
                            "count_both": count_both,
                        }
                    )

    rules.sort(key=lambda r: (r["lift"], r["confidence"]), reverse=True)
    return rules


def format_rules_table(
    rules: List[Dict],
    top_n: int = 20,
    sort_by: str = "lift",
) -> str:
    """Format association rules as a readable markdown table.

    Args:
        rules: List of rule dicts from generate_association_rules().
        top_n: Number of top rules to show.
        sort_by: Sort key — 'lift', 'confidence', or 'support'.
    """
    if not rules:
        return "No association rules found."

    sorted_rules = sorted(rules, key=lambda r: r[sort_by], reverse=True)[:top_n]

    lines = [
        f"| # | Antecedent | Consequent | Support | Confidence | Lift |",
        f"|---|------------|-------------|---------|------------|------|",
    ]
    for i, r in enumerate(sorted_rules, 1):
        ant = ", ".join(r["antecedent"])
        cons = ", ".join(r["consequent"])
        lines.append(
            f"| {i} | {ant} | {cons} | {r['support']:.3f} | "
            f"{r['confidence']:.3f} | {r['lift']:.2f} |"
        )

    return "\n".join(lines)


def generate_closed_itemsets(
    transactions: List[Set[str]],
    min_support: float = 0.0,
) -> List[Tuple[Tuple[str, ...], float]]:
    """Generate closed itemsets from formal concept analysis.

    Closed itemsets are intents of formal concepts — they are lossless:
    all frequent itemsets can be recovered from the closed ones and their supports.
    This bridges Apriori with FCA: closed itemsets are strictly more principled
    than arbitrary frequent itemsets.

    Uses lazy import to avoid circular dependencies with grouptheory.py.
    """
    from tools.analytics.grouptheory import FormalContext, enumerate_concepts

    ctx = FormalContext(transactions)
    concepts = enumerate_concepts(ctx, min_support=min_support)
    return [(c.intent, c.support) for c in concepts]
