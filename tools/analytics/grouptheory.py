"""Group Theory integration for knowledge base structural analysis.

Adds Formal Concept Analysis (FCA), Galois connections, equivalence classes,
implication bases, sublattice completeness, and cross-domain symmetry detection
to the existing Apriori association rule mining pipeline.

All algorithms are pure Python. No third-party dependencies.

Mathematical foundation:
  - Formal Context K = (G, M, I) where G = transactions, M = items
  - Galois connection: object_derivation (B') and attribute_derivation (A')
  - Closure operator: B'' gives ALL items necessarily present when B is present
  - Concept lattice B(K): all (extent, intent) pairs satisfying A' = B and B' = A
  - Duquenne-Guigues basis: canonical minimal implication base
"""

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Set, Tuple, Optional, FrozenSet


# ─── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class FormalContext:
    """A formal context K = (G, M, I) for FCA.

    G = transactions (objects), M = items (attributes), I = incidence relation.
    """
    transactions: List[Set[str]]
    all_items: List[str] = field(default_factory=list)
    item_to_idx: Dict[str, int] = field(default_factory=dict)
    n_transactions: int = 0
    n_items: int = 0

    def __post_init__(self):
        self.n_transactions = len(self.transactions)
        if not self.all_items:
            all_items_set: Set[str] = set()
            for txn in self.transactions:
                all_items_set.update(txn)
            self.all_items = sorted(all_items_set)
        if not self.item_to_idx:
            self.item_to_idx = {item: i for i, item in enumerate(self.all_items)}
        self.n_items = len(self.all_items)


@dataclass(frozen=True)
class FormalConcept:
    """A formal concept (A, B) where A' = B and B' = A (maximal rectangle)."""
    extent: Tuple[int, ...]      # transaction indices
    intent: Tuple[str, ...]      # items (closed set)
    support: float                # |extent| / |G|


@dataclass(frozen=True)
class Implication:
    """A logical implication P -> C: every transaction with P also has C."""
    premise: Tuple[str, ...]
    conclusion: Tuple[str, ...]
    support: float                # fraction of txns where premise holds
    confidence: float             # always 1.0 for valid implications


@dataclass
class KnowledgeGap:
    """A structural gap in the concept lattice — missing knowledge combination."""
    items: Tuple[str, ...]
    n_items: int
    pairwise_pairs: List[Tuple[Tuple[str, ...], bool]]
    full_cooccurs: bool
    severity: str                 # "critical" (all pairs OK but full set missing)


@dataclass
class SymmetryGroup:
    """Items from different domains that play the same structural role."""
    items: List[str]
    domain_labels: Dict[str, str]
    structural_signature: str
    interpretation: str


@dataclass
class EquivalenceClass:
    """Items that appear in exactly the same set of transactions."""
    class_id: int
    items: List[str]
    transaction_indices: Tuple[int, ...]
    support: float
    interpretation: str           # "substitutable" / "always used together"


# ─── Galois Operators ──────────────────────────────────────────────────────────

def object_derivation(ctx: FormalContext, items: Set[str]) -> Set[int]:
    """B' = {g in G | for all m in B: (g,m) in I}.

    Returns indices of ALL transactions containing every item in `items`.
    Empty B → all transaction indices. No matching txns → empty set.
    """
    if not items:
        return set(range(ctx.n_transactions))

    idxs = set(range(ctx.n_transactions))
    for item in items:
        item_idxs = {
            i for i in range(ctx.n_transactions) if item in ctx.transactions[i]
        }
        idxs &= item_idxs
        if not idxs:
            return set()
    return idxs


def attribute_derivation(ctx: FormalContext, txn_indices: Set[int]) -> Set[str]:
    """A' = {m in M | for all g in A: (g,m) in I}.

    Returns items that appear in EVERY transaction in `txn_indices`.
    Empty A → all items (vacuously true).
    """
    if not txn_indices:
        return set(ctx.all_items)

    result = set(ctx.all_items)
    for i in txn_indices:
        result &= ctx.transactions[i]
        if not result:
            return set()
    return result


def attribute_closure(ctx: FormalContext, items: Set[str]) -> Set[str]:
    """B'' — Galois closure on attribute sets.

    Returns ALL items that appear in EVERY transaction containing ALL of `items`.
    "If these items are present, what else is GUARANTEED to also be present?"
    """
    txn_idxs = object_derivation(ctx, items)
    return attribute_derivation(ctx, txn_idxs)


def object_closure(ctx: FormalContext, txn_indices: Set[int]) -> Set[int]:
    """A'' — Galois closure on object (transaction) sets."""
    attrs = attribute_derivation(ctx, txn_indices)
    return object_derivation(ctx, attrs)


def is_closed(ctx: FormalContext, items: Set[str]) -> bool:
    """A set is closed iff it equals its own closure. closure(X) == X."""
    return attribute_closure(ctx, items) == items


# ─── Closure Cache ─────────────────────────────────────────────────────────────

def _build_closure_cache(
    ctx: FormalContext, min_support: float = 0.0
) -> Dict[FrozenSet[str], Set[str]]:
    """Pre-compute closures for all item singletons.

    Not all closures (2^|M|), just singletons — full closures computed
    on-demand in NextClosure. This cache speeds up the lectic order traversal
    by memoizing computed closures.
    """
    cache: Dict[FrozenSet[str], Set[str]] = {}
    min_count = min_support if min_support >= 1 else int(min_support * ctx.n_transactions)
    if min_count < 1:
        min_count = 0

    for item in ctx.all_items:
        closed = attribute_closure(ctx, {item})
        if len(object_derivation(ctx, closed)) >= min_count:
            cache[frozenset({item})] = closed
    return cache


# ─── NextClosure Concept Enumeration ───────────────────────────────────────────

def enumerate_concepts(
    ctx: FormalContext,
    min_support: float = 0.0,
    max_concepts: int = 2000,
) -> List[FormalConcept]:
    """Enumerate all formal concepts using Ganter's NextClosure algorithm.

    Traverses closed attribute sets in lectic (colexicographic) order.
    Each closed set B yields concept (B', B).

    Args:
        ctx: Formal context.
        min_support: Minimum support threshold (fraction or absolute count).
        max_concepts: Safety cap to prevent unbounded enumeration.

    Returns:
        List of FormalConcept sorted by intent size ascending.
    """
    n_items = ctx.n_items
    if ctx.n_transactions == 0:
        return []

    min_count = min_support if min_support >= 1 else int(min_support * ctx.n_transactions)
    if min_count < 1:
        min_count = 0

    # closure with support filtering
    closure_cache: Dict[FrozenSet[str], FrozenSet[str]] = {}

    def close(items: FrozenSet[str]) -> FrozenSet[str]:
        if items in closure_cache:
            return closure_cache[items]
        result = frozenset(attribute_closure(ctx, set(items)))
        closure_cache[items] = result
        return result

    concepts: List[FormalConcept] = []
    seen_intents: Set[FrozenSet[str]] = set()

    # Start: closure of empty set (items present in ALL transactions)
    current = close(frozenset())
    seen_intents.add(current)
    extent_current = object_derivation(ctx, set(current))
    if len(extent_current) >= min_count:
        concepts.append(FormalConcept(
            extent=tuple(sorted(extent_current)),
            intent=tuple(sorted(current)),
            support=len(extent_current) / ctx.n_transactions,
        ))

    # NextClosure in lectic order
    items_list = ctx.all_items

    while len(concepts) < max_concepts:
        # Try to find the next closed set in lectic order
        found = False
        for i in range(n_items - 1, -1, -1):
            item_i = items_list[i]
            if item_i in current:
                continue
            # B = (current ∩ {0..i-1}) ∪ {i}
            prefix = {items_list[j] for j in range(i) if items_list[j] in current}
            prefix.add(item_i)
            B = close(frozenset(prefix))

            # Lectic: all new elements must be >= i
            new_elements = B - current
            if new_elements and min(idx for idx, it in enumerate(items_list) if it in new_elements) >= i:
                if B not in seen_intents:
                    extent_B = object_derivation(ctx, set(B))
                    if len(extent_B) >= min_count:
                        seen_intents.add(B)
                        concepts.append(FormalConcept(
                            extent=tuple(sorted(extent_B)),
                            intent=tuple(sorted(B)),
                            support=len(extent_B) / ctx.n_transactions,
                        ))
                    current = B
                    found = True
                    break

        if not found:
            break  # reached maximal element

    return concepts


def build_lattice(
    ctx: FormalContext,
    min_support: float = 0.0,
    max_concepts: int = 2000,
) -> Dict:
    """Build the concept lattice from a formal context.

    Returns:
        Dict with keys: concepts, concept_count, edges, height,
        top_concept_idx, bottom_concept_idx.
    """
    concepts = enumerate_concepts(ctx, min_support=min_support, max_concepts=max_concepts)

    # Sort by intent size ascending (bottom = smallest intent = largest extent)
    concepts_by_intent_size = sorted(enumerate(concepts), key=lambda x: len(x[1].intent))

    # Build edge relation: C is subconcept of D if intent(C) ⊂ intent(D)
    # and no intermediate concept exists
    n = len(concepts)
    edges: List[Tuple[int, int]] = []

    for i, ci in enumerate(concepts):
        intent_i = set(ci.intent)
        candidates = [
            (j, cj) for j, cj in enumerate(concepts)
            if i != j and intent_i.issubset(set(cj.intent))
        ]
        # Find direct superconcepts (minimal supersets)
        for j, cj in candidates:
            intent_j = set(cj.intent)
            # Check for intermediate: any concept whose intent is between intent_i and intent_j
            has_intermediate = False
            for k, ck in enumerate(concepts):
                if k == i or k == j:
                    continue
                intent_k = set(ck.intent)
                if intent_i.issubset(intent_k) and intent_k.issubset(intent_j) and intent_k != intent_i and intent_k != intent_j:
                    has_intermediate = True
                    break
            if not has_intermediate:
                edges.append((i, j))

    # Height: longest chain
    height = 0
    if n > 0:
        heights = [0] * n
        for i, ci in enumerate(concepts):
            for parent, child in edges:
                heights[child] = max(heights[child], heights[parent] + 1)
        height = max(heights) if heights else 0

    # Top = largest extent, smallest intent; Bottom = smallest extent, largest intent
    top_idx = min(range(n), key=lambda i: len(concepts[i].intent)) if n else -1
    bottom_idx = max(range(n), key=lambda i: len(concepts[i].intent)) if n else -1

    return {
        "concepts": concepts,
        "concept_count": n,
        "edges": edges,
        "height": height,
        "top_concept_idx": top_idx,
        "bottom_concept_idx": bottom_idx,
    }


def find_concept_for_items(
    ctx: FormalContext,
    lattice: Dict,
    items: List[str],
) -> Optional[FormalConcept]:
    """Find the concept whose intent best matches the given items."""
    closed = attribute_closure(ctx, set(items))
    closed_tuple = tuple(sorted(closed))
    for concept in lattice["concepts"]:
        if concept.intent == closed_tuple:
            return concept
    return None


# ─── Equivalence Classes ───────────────────────────────────────────────────────

def compute_equivalence_classes(ctx: FormalContext) -> List[EquivalenceClass]:
    """Partition items by their transaction support set.

    Items in the same class appear in exactly the same set of transactions.
    They are extensionally equivalent (always used together, fully substitutable).
    """
    # Compute transaction support set for each item
    item_txns: Dict[str, FrozenSet[int]] = {}
    for item in ctx.all_items:
        txns = frozenset(
            i for i in range(ctx.n_transactions) if item in ctx.transactions[i]
        )
        item_txns[item] = txns

    # Group by support set
    groups: Dict[FrozenSet[int], List[str]] = defaultdict(list)
    for item, txns in item_txns.items():
        groups[txns].append(item)

    # Build equivalence classes
    classes = []
    class_id = 0
    for txns, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        if len(items) < 2:
            continue
        support = len(txns) / max(ctx.n_transactions, 1)
        interpretation = (
            "substitutable" if support > 0.5 else "always used together"
        )
        classes.append(EquivalenceClass(
            class_id=class_id,
            items=sorted(items),
            transaction_indices=tuple(sorted(txns)),
            support=support,
            interpretation=interpretation,
        ))
        class_id += 1

    return classes


def detect_potential_synonyms(
    ctx: FormalContext, min_jaccard: float = 0.8
) -> List[Tuple[str, str, float]]:
    """Find item pairs that are near-equivalent (Jaccard similarity > threshold).

    These differ in only a few files — potential tag synonyms or tool aliases.
    """
    item_txns: Dict[str, Set[int]] = {}
    for item in ctx.all_items:
        item_txns[item] = {
            i for i in range(ctx.n_transactions) if item in ctx.transactions[i]
        }

    results = []
    items_list = sorted(ctx.all_items)
    for i in range(len(items_list)):
        for j in range(i + 1, len(items_list)):
            a, b = items_list[i], items_list[j]
            set_a, set_b = item_txns[a], item_txns[b]
            union = len(set_a | set_b)
            if union == 0:
                continue
            jaccard = len(set_a & set_b) / union
            if jaccard >= min_jaccard and jaccard < 1.0:
                results.append((a, b, round(jaccard, 4)))

    results.sort(key=lambda x: -x[2])
    return results


# ─── Implication Basis (Duquenne-Guigues) ──────────────────────────────────────

def _pseudo_intent_check(
    ctx: FormalContext,
    P: FrozenSet[str],
    pseudo_intents: List[FrozenSet[str]],
) -> bool:
    """Check if P is a pseudo-intent: P != P'' and for all Q ⊂ P (pseudo-intent), Q'' ⊂ P."""
    P_set = set(P)
    P_closed = attribute_closure(ctx, P_set)

    # Condition 1: P != P'' (P is not closed)
    if P_set == P_closed:
        return False

    # Condition 2: for every smaller pseudo-intent Q ⊂ P, Q'' ⊂ P
    for Q in pseudo_intents:
        if Q.issubset(P_set) and Q != P:
            Q_closed = attribute_closure(ctx, set(Q))
            if not Q_closed.issubset(P_set):
                return False

    return True


def compute_implication_basis(
    ctx: FormalContext,
    min_support: float = 0.0,
) -> List[Implication]:
    """Compute the Duquenne-Guigues canonical implication basis.

    Uses NextClosure on the set of pseudo-intents. The result is a minimal set
    of implications from which ALL valid implications logically follow.
    Every rule has confidence = 1.0 (logical necessity, not just statistical).

    Args:
        ctx: Formal context.
        min_support: Minimum support for premise items.

    Returns:
        List of Implication, sorted by support descending.
    """
    min_count = min_support if min_support >= 1 else int(min_support * ctx.n_transactions)
    if min_count < 1:
        min_count = 0

    n_items = ctx.n_items
    items_list = ctx.all_items
    pseudo_intents: List[FrozenSet[str]] = []
    implications: List[Implication] = []

    # closure cache
    closure_cache: Dict[FrozenSet[str], FrozenSet[str]] = {}

    def close(items: FrozenSet[str]) -> FrozenSet[str]:
        if items in closure_cache:
            return closure_cache[items]
        result = frozenset(attribute_closure(ctx, set(items)))
        closure_cache[items] = result
        return result

    # Start with empty set
    current = close(frozenset())
    if current != frozenset():
        # closure of empty -> items in ALL transactions
        extent_empty = object_derivation(ctx, set(current))
        if len(extent_empty) >= min_count:
            implications.append(Implication(
                premise=(),
                conclusion=tuple(sorted(current)),
                support=len(extent_empty) / ctx.n_transactions,
                confidence=1.0,
            ))

    # NextClosure on pseudo-intents
    max_iterations = 5000
    for _ in range(max_iterations):
        found = False
        for i in range(n_items - 1, -1, -1):
            item_i = items_list[i]
            if item_i in current:
                continue
            prefix = {items_list[j] for j in range(i) if items_list[j] in current}
            prefix.add(item_i)
            candidate = frozenset(prefix)

            if _pseudo_intent_check(ctx, candidate, pseudo_intents):
                closed_set = close(candidate)
                extent = object_derivation(ctx, set(closed_set))
                if len(extent) >= min_count:
                    premise_items = set(candidate)
                    conclusion_items = set(closed_set) - premise_items
                    if conclusion_items:
                        implications.append(Implication(
                            premise=tuple(sorted(premise_items)),
                            conclusion=tuple(sorted(conclusion_items)),
                            support=len(extent) / ctx.n_transactions,
                            confidence=1.0,
                        ))
                    pseudo_intents.append(candidate)
                current = closed_set
                found = True
                break

        if not found:
            break

    implications.sort(key=lambda r: (r.support, len(r.premise)), reverse=True)
    return implications


def validate_implication(
    ctx: FormalContext,
    premise: List[str],
    conclusion: List[str],
) -> Tuple[bool, float]:
    """Check if an implication is valid in the current context.

    Returns:
        (is_valid, support) — support = fraction of txns where premise holds.
    """
    premise_set = set(premise)
    premise_txns = object_derivation(ctx, premise_set)
    support = len(premise_txns) / max(ctx.n_transactions, 1)

    if not premise_txns:
        return True, support  # vacuously true

    for txn_idx in premise_txns:
        for item in conclusion:
            if item not in ctx.transactions[txn_idx]:
                return False, support
    return True, support


# ─── Sublattice Completeness / Knowledge Gap Detection ─────────────────────────

def detect_sublattice_gaps(
    ctx: FormalContext,
    max_size: int = 4,
    min_item_freq: int = 3,
) -> List[KnowledgeGap]:
    """Detect structural gaps in the concept lattice.

    A critical gap: all k-1 sized subsets of an itemset co-occur, but the
    full k-sized set never appears together in any transaction. This means
    the knowledge base has "pairwise coverage" but lacks "joint coverage."

    Args:
        ctx: Formal context.
        max_size: Maximum itemset size to check.
        min_item_freq: Only consider items appearing in >= min_item_freq txns.

    Returns:
        List of KnowledgeGap sorted by severity (critical first).
    """
    # Filter to frequent items only
    freq_items = [
        item for item in ctx.all_items
        if sum(1 for t in ctx.transactions if item in t) >= min_item_freq
    ]

    gaps = []

    for k in range(3, min(max_size + 1, len(freq_items) + 1)):
        # Limit combinatorial explosion: if too many candidates, sample
        candidates = list(combinations(freq_items, k))
        if len(candidates) > 5000:
            # Pre-filter: only check sets where all items have high co-occurrence density
            candidates = _filter_dense_candidates(ctx, candidates, freq_items)

        for itemset in candidates[:5000]:  # hard cap
            itemset_set = set(itemset)
            # Check pairwise co-occurrence
            pairwise_results = []
            all_pairs_ok = True
            for a, b in combinations(itemset, 2):
                pair_cooccurs = any(
                    a in t and b in t for t in ctx.transactions
                )
                pairwise_results.append(((a, b), pair_cooccurs))
                if not pair_cooccurs:
                    all_pairs_ok = False

            # Check full co-occurrence
            full_cooccurs = any(
                itemset_set.issubset(t) for t in ctx.transactions
            )

            if not full_cooccurs:
                severity = "critical" if all_pairs_ok else "partial"
                gaps.append(KnowledgeGap(
                    items=tuple(sorted(itemset)),
                    n_items=k,
                    pairwise_pairs=pairwise_results,
                    full_cooccurs=False,
                    severity=severity,
                ))

    gaps.sort(key=lambda g: (0 if g.severity == "critical" else 1, -g.n_items))
    return gaps


def _filter_dense_candidates(
    ctx: FormalContext,
    candidates: List[Tuple[str, ...]],
    freq_items: List[str],
) -> List[Tuple[str, ...]]:
    """Pre-filter candidates to those with higher co-occurrence density."""
    # Compute co-occurrence matrix for frequent items
    cooccur: Dict[str, Set[str]] = defaultdict(set)
    for txn in ctx.transactions:
        txn_freq = [it for it in txn if it in set(freq_items)]
        for a in txn_freq:
            for b in txn_freq:
                if a != b:
                    cooccur[a].add(b)

    scored = []
    for itemset in candidates:
        total_pairs = 0
        connected_pairs = 0
        for a, b in combinations(itemset, 2):
            total_pairs += 1
            if b in cooccur.get(a, set()):
                connected_pairs += 1
        density = connected_pairs / total_pairs if total_pairs > 0 else 0
        scored.append((density, itemset))

    scored.sort(key=lambda x: -x[0])
    # Return top 3000 by density
    return [itemset for _, itemset in scored[:3000]]


# ─── Cross-Domain Symmetry Analysis ────────────────────────────────────────────

def compute_structural_signature(ctx: FormalContext, item: str) -> Dict:
    """Compute a structural fingerprint for an item based on its lattice position.

    Features: support, degree (co-occurring items count), number of co-occurring
    items, and abstract lattice properties.
    """
    item_txns = {i for i in range(ctx.n_transactions) if item in ctx.transactions[i]}
    support = len(item_txns) / max(ctx.n_transactions, 1)

    cooccurring = set()
    for txn_idx in item_txns:
        for other in ctx.transactions[txn_idx]:
            if other != item:
                cooccurring.add(other)

    return {
        "support": round(support, 4),
        "degree": len(cooccurring),
        "cooccurring_items": len(cooccurring),
        "txn_count": len(item_txns),
    }


def detect_domain_analogues(
    ctx: FormalContext,
    domain_labels: Dict[str, str],
    min_similarity: float = 0.7,
) -> List[SymmetryGroup]:
    """Find items from different domains that play the same structural role.

    Two items are domain-analogues if they have similar structural signatures
    (support, degree, txn_count) but belong to different domains.

    Args:
        ctx: Formal context.
        domain_labels: {item_name: domain_label} mapping.
        min_similarity: Cosine similarity threshold for grouping.

    Returns:
        List of SymmetryGroup.
    """
    # Only consider items with domain labels
    labeled_items = [
        item for item in ctx.all_items if item in domain_labels
    ]
    if len(labeled_items) < 2:
        return []

    # Compute signatures
    sigs = {item: compute_structural_signature(ctx, item) for item in labeled_items}

    # Vectorize: [support, normalized_degree]
    max_degree = max(s["degree"] for s in sigs.values()) if sigs else 1
    vectors = {}
    for item, sig in sigs.items():
        vectors[item] = (
            sig["support"],
            sig["degree"] / max(max_degree, 1),
        )

    # Group by cosine similarity clustering
    groups: List[List[str]] = []
    assigned: Set[str] = set()

    for item in labeled_items:
        if item in assigned:
            continue
        group = [item]
        for other in labeled_items:
            if other in assigned or other == item:
                continue
            v1, v2 = vectors[item], vectors[other]
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            norm1 = (v1[0]**2 + v1[1]**2) ** 0.5
            norm2 = (v2[0]**2 + v2[1]**2) ** 0.5
            sim = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0
            if sim >= min_similarity:
                group.append(other)
                assigned.add(other)
        if len(group) >= 2:
            groups.append(group)
        assigned.add(item)

    # Build SymmetryGroups
    result = []
    for group in groups:
        domains_in_group = {
            item: domain_labels.get(item, "unknown") for item in group
        }
        unique_domains = set(domains_in_group.values())
        if len(unique_domains) >= 2:
            sig = sigs[group[0]]
            result.append(SymmetryGroup(
                items=sorted(group),
                domain_labels=domains_in_group,
                structural_signature=f"support={sig['support']:.3f}, degree={sig['degree']}",
                interpretation=f"跨域结构同构: {', '.join(sorted(unique_domains))}",
            ))

    return result


# ─── Comparison with Apriori ───────────────────────────────────────────────────

def compare_with_apriori(
    ctx: FormalContext,
    apriori_frequent: Dict[Tuple[str, ...], float],
    min_support: float = 0.0,
) -> Dict:
    """Compare Apriori's frequent itemsets with formal concepts.

    Key insight: "frequent but not closed" itemsets miss the logical closure.
    Apriori says X is frequent. Closure says X'' necessarily accompanies X.
    """
    concepts = enumerate_concepts(ctx, min_support=min_support)

    # All closed intents from concepts
    closed_intents: Set[FrozenSet[str]] = {
        frozenset(c.intent) for c in concepts
    }

    # Apriori itemsets
    apriori_sets: Set[FrozenSet[str]] = {
        frozenset(itemset) for itemset in apriori_frequent.keys()
    }

    closed_and_frequent = apriori_sets & closed_intents
    frequent_not_closed = apriori_sets - closed_intents
    closed_not_frequent = closed_intents - apriori_sets

    # Enrichment examples: for frequent-but-not-closed sets, show what the closure adds
    enrichment_examples = []
    for fs in sorted(frequent_not_closed, key=lambda x: -len(x))[:5]:
        closed = frozenset(attribute_closure(ctx, set(fs)))
        added = tuple(sorted(closed - fs))
        if added:
            enrichment_examples.append({
                "itemset": tuple(sorted(fs)),
                "closed_intent": tuple(sorted(closed)),
                "added_items": added,
                "support": apriori_frequent.get(tuple(sorted(fs)), 0),
            })

    return {
        "apriori_itemsets_count": len(apriori_sets),
        "closed_concepts_count": len(closed_intents),
        "closed_but_not_frequent": len(closed_not_frequent),
        "frequent_but_not_closed": len(frequent_not_closed),
        "overlap_count": len(closed_and_frequent),
        "closure_enrichment_examples": enrichment_examples,
    }


# ─── Recommendation by Closure ─────────────────────────────────────────────────

def recommend_by_closure(
    ctx: FormalContext,
    known_items: List[str],
) -> List[Dict]:
    """Recommend items using Galois closure instead of association rules.

    Given known context items, compute their closure. Items in the closure
    but not in the input are LOGICALLY NECESSARY (they appear in EVERY
    transaction that contains all known items).

    This is fundamentally different from Apriori: closure = logical necessity,
    not probabilistic co-occurrence.
    """
    known_set = set(known_items)
    closed = attribute_closure(ctx, known_set)
    new_items = closed - known_set

    if not new_items:
        return []

    # Score: support of the joint set
    joint_txns = object_derivation(ctx, known_set)
    joint_support = len(joint_txns) / max(ctx.n_transactions, 1)

    recommendations = []
    for item in sorted(new_items):
        recommendations.append({
            "item": item,
            "score": round(joint_support, 4),
            "rationale": f"必然伴随: 所有包含 {{{', '.join(sorted(known_set))}}} 的案例都包含 {item}",
            "certainty": "logically_necessary",
            "joint_support": joint_support,
        })

    recommendations.sort(key=lambda r: r["score"], reverse=True)
    return recommendations


# ─── Comprehensive Analysis ────────────────────────────────────────────────────

def analyze_comprehensively(
    ctx: FormalContext,
    apriori_frequent: Optional[Dict[Tuple[str, ...], float]] = None,
    domain_labels: Optional[Dict[str, str]] = None,
    min_support: float = 0.05,
) -> Dict:
    """Run all group-theoretic analyses on a formal context.

    Returns a dict with all analysis results for reporting.
    """
    result: Dict = {
        "context_summary": {
            "n_transactions": ctx.n_transactions,
            "n_items": ctx.n_items,
            "avg_txn_size": round(
                sum(len(t) for t in ctx.transactions) / max(ctx.n_transactions, 1), 1
            ),
        },
    }

    # Equivalence classes
    eq_classes = compute_equivalence_classes(ctx)
    result["equivalence_classes"] = eq_classes
    result["n_equivalence_classes"] = len(eq_classes)
    result["n_equivalent_items"] = sum(len(c.items) for c in eq_classes)

    # Near-synonyms
    synonyms = detect_potential_synonyms(ctx)
    result["potential_synonyms"] = synonyms[:20]

    # Implication basis
    basis = compute_implication_basis(ctx, min_support=min_support)
    result["implication_basis"] = basis
    result["n_implications"] = len(basis)

    # Knowledge gaps
    gaps = detect_sublattice_gaps(ctx, max_size=4)
    critical_gaps = [g for g in gaps if g.severity == "critical"]
    result["knowledge_gaps"] = gaps[:30]
    result["n_gaps_total"] = len(gaps)
    result["n_critical_gaps"] = len(critical_gaps)

    # Lattice summary
    lattice = build_lattice(ctx, min_support=min_support)
    result["lattice_summary"] = {
        "concept_count": lattice["concept_count"],
        "height": lattice["height"],
        "edge_count": len(lattice["edges"]),
    }

    # Apriori comparison (if frequent itemsets provided)
    if apriori_frequent:
        comparison = compare_with_apriori(ctx, apriori_frequent, min_support)
        result["apriori_comparison"] = comparison

    # Cross-domain symmetry (if domain labels provided)
    if domain_labels:
        symmetry = detect_domain_analogues(ctx, domain_labels)
        result["symmetry_groups"] = symmetry
        result["n_symmetry_groups"] = len(symmetry)

    return result


# ─── Formatters ────────────────────────────────────────────────────────────────

def format_lattice_summary(lattice: Dict) -> str:
    """Format lattice metadata as markdown."""
    lines = [
        "## 概念格摘要",
        "",
        f"- 概念数: {lattice['concept_count']}",
        f"- 格高度: {lattice['height']}",
        f"- 边数: {len(lattice['edges'])}",
    ]
    if lattice["concept_count"] > 0:
        top = lattice["concepts"][lattice["top_concept_idx"]]
        bottom = lattice["concepts"][lattice["bottom_concept_idx"]]
        lines.append(f"- top concept (max extent): {len(top.extent)} txns, intent={list(top.intent)[:5]}...")
        lines.append(f"- bottom concept (min extent): {len(bottom.extent)} txns, intent={list(bottom.intent)[:5]}...")
    return "\n".join(lines)


def format_implication_basis(basis: List[Implication], top_n: int = 30) -> str:
    """Format implication basis as markdown table."""
    if not basis:
        return "No implications found."

    shown = basis[:top_n]
    lines = [
        f"## 蕴含基 (Duquenne-Guigues Basis)",
        f"",
        f"共 {len(basis)} 条逻辑规则（所有规则置信度 = 100%）",
        f"",
        f"| # | 前提 | 结论 | 支持度 |",
        f"|---|---|---|---|",
    ]
    for i, imp in enumerate(shown, 1):
        prem = ", ".join(imp.premise) if imp.premise else "(空/全局)"
        cons = ", ".join(imp.conclusion)
        lines.append(f"| {i} | {prem} | **{cons}** | {imp.support:.3f} |")

    lines.append("")
    lines.append("### 解读")
    lines.append("")
    for i, imp in enumerate(shown[:5], 1):
        if imp.premise:
            prem = ", ".join(imp.premise)
            cons = ", ".join(imp.conclusion)
            lines.append(
                f"- **规则{i}**: 当交易中出现 {{{prem}}} 时，**必然**也出现 {{{cons}}}。"
                f"（支持度 {imp.support:.1%}）"
            )
        else:
            cons = ", ".join(imp.conclusion)
            lines.append(
                f"- **规则{i}** (全局): 所有交易中必然出现 {{{cons}}}。"
            )
    return "\n".join(lines)


def format_gaps(gaps: List[KnowledgeGap], top_n: int = 20) -> str:
    """Format knowledge gaps as markdown."""
    if not gaps:
        return "No knowledge gaps detected."

    critical = [g for g in gaps if g.severity == "critical"]
    partial = [g for g in gaps if g.severity == "partial"]

    lines = [
        f"## 知识盲区检测",
        f"",
        f"- **严重缺口 (Critical)**: {len(critical)} — 所有子对都有覆盖，但全组合缺失",
        f"- **部分缺口 (Partial)**: {len(partial)} — 部分子对缺失",
        f"",
    ]

    if critical:
        lines.append("### 严重缺口（优先填补）")
        lines.append("")
        lines.append("| # | 缺失组合 | 大小 | 状态 |")
        lines.append("|---|---|---|---|")
        for i, gap in enumerate(critical[:top_n], 1):
            items_str = ", ".join(gap.items)
            all_ok = all(ok for _, ok in gap.pairwise_pairs)
            status = "所有子对有覆盖" if all_ok else "部分子对有覆盖"
            lines.append(f"| {i} | {items_str} | {gap.n_items} | {status} |")

    return "\n".join(lines)


def format_symmetry_groups(groups: List[SymmetryGroup]) -> str:
    """Format symmetry groups as markdown."""
    if not groups:
        return "No cross-domain symmetry groups detected."

    lines = [
        f"## 跨域对称分析",
        f"",
        f"共 {len(groups)} 组跨域结构同构",
        f"",
    ]
    for i, g in enumerate(groups, 1):
        lines.append(f"### 对称组 {i}: {g.interpretation}")
        lines.append(f"- 结构签名: {g.structural_signature}")
        lines.append(f"- 成员:")
        for item in g.items:
            dom = g.domain_labels.get(item, "?")
            lines.append(f"  - `{item}` (域: {dom})")
        lines.append("")

    return "\n".join(lines)


def format_comparison(comparison: Dict) -> str:
    """Format Apriori vs FCA comparison as markdown."""
    lines = [
        "## Apriori vs 形式概念分析 (FCA)",
        "",
        f"| 指标 | 值 |",
        f"|---|---|",
        f"| Apriori 频繁项集数 | {comparison['apriori_itemsets_count']} |",
        f"| 闭概念数 (FCA) | {comparison['closed_concepts_count']} |",
        f"| 闭集且频繁 | {comparison['overlap_count']} |",
        f"| 频繁但不闭 | {comparison['frequent_but_not_closed']} |",
        f"| 闭但不频繁 | {comparison['closed_but_not_frequent']} |",
        f"",
    ]

    if comparison["frequent_but_not_closed"] > 0:
        lines.append(
            f"**{comparison['frequent_but_not_closed']} 个Apriori频繁项集不是闭集** "
            f"— 它们的闭包包含额外的必然伴随项，Apriori漏掉了这些。"
        )
        lines.append("")

    examples = comparison.get("closure_enrichment_examples", [])
    if examples:
        lines.append("### 闭包富集示例")
        lines.append("")
        for ex in examples:
            added = ", ".join(ex["added_items"])
            itemset = ", ".join(ex["itemset"])
            lines.append(
                f"- Apriori说 `{{{itemset}}}` 频繁 (sup={ex['support']:.3f})，"
                f"但闭包揭示还必然伴随: **{added}**"
            )

    return "\n".join(lines)


def format_equivalence_classes(classes: List[EquivalenceClass], top_n: int = 15) -> str:
    """Format equivalence classes as markdown."""
    if not classes:
        return "No equivalence classes found (all items have unique transaction sets)."

    lines = [
        f"## 等价类分析",
        f"",
        f"共 {len(classes)} 个等价类（>1项的组）",
        f"",
        f"| # | 成员 | 支持度 | 解释 |",
        f"|---|---|---|---|",
    ]
    for c in classes[:top_n]:
        members = ", ".join(c.items[:5])
        if len(c.items) > 5:
            members += f" ... (+{len(c.items) - 5})"
        lines.append(f"| {c.class_id + 1} | {members} | {c.support:.3f} | {c.interpretation} |")

    return "\n".join(lines)


def format_closure_result(
    known_items: List[str],
    closed_items: Set[str],
    recommendations: List[Dict],
) -> str:
    """Format closure computation results."""
    new_items = closed_items - set(known_items)
    lines = [
        "## Galois 闭包分析",
        "",
        f"**输入项**: {', '.join(known_items)}",
        f"**闭包大小**: {len(closed_items)}",
        f"**新发现项**: {len(new_items)}",
        "",
    ]
    if new_items:
        lines.append("以下项**必然**伴随出现（在所有包含输入项的交易中）：")
        lines.append("")
        for item in sorted(new_items):
            lines.append(f"- **{item}**")
    else:
        lines.append("输入项是闭合的——没有额外的必然伴随项。")

    if recommendations:
        lines.append("")
        lines.append("| 推荐项 | 必然性 | 联合支持度 |")
        lines.append("|---|---|---|")
        for rec in recommendations:
            lines.append(f"| {rec['item']} | {rec['certainty']} | {rec['joint_support']:.3f} |")

    return "\n".join(lines)
