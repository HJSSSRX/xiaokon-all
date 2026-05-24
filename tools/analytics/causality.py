"""Causal Inference & Abductive Reasoning — 因果推断 / 逆向推理.

Provides:
  1. Causal graph construction from Apriori rules + domain knowledge
  2. Abductive inference: P(cause | observed effects) via Bayesian inversion
  3. Counterfactual reasoning: "what if" across domains via isomorphisms
  4. Simplified causal discovery (PC-like) from transaction data
  5. Root-cause tracing and intervention effect estimation

Core principle:
  - Deduction: cause → effect (forward, "if domain=crypto then tool=sage")
  - Induction: effect ... effect → pattern (mining, "sage co-occurs with rsa")
  - Abduction: effect → cause (backward, "sage is used, therefore likely crypto")
"""

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Set, Tuple, FrozenSet, Optional, Any
import math


# ─── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class CausalEdge:
    """A directed causal edge: cause → effect."""
    cause: str
    effect: str
    strength: float       # causal strength (0-1), derived from rule confidence
    support: float        # P(cause ∧ effect)
    edge_type: str = ""   # "direct", "domain_knowledge", "discovered", "isomorphism"
    rationale: str = ""


@dataclass
class CausalGraph:
    """A directed causal graph over features.

    Nodes = feature names (tools, tags, techniques, domains)
    Edges = causal relationships with strengths
    """
    nodes: Set[str] = field(default_factory=set)
    edges: List[CausalEdge] = field(default_factory=list)
    # Adjacency: node → [(target, edge_index)]
    outgoing: Dict[str, List[Tuple[str, int]]] = field(default_factory=dict)
    incoming: Dict[str, List[Tuple[str, int]]] = field(default_factory=dict)
    node_types: Dict[str, str] = field(default_factory=dict)

    def add_edge(self, edge: CausalEdge):
        idx = len(self.edges)
        self.edges.append(edge)
        self.nodes.add(edge.cause)
        self.nodes.add(edge.effect)
        self.outgoing.setdefault(edge.cause, []).append((edge.effect, idx))
        self.incoming.setdefault(edge.effect, []).append((edge.cause, idx))

    def parents(self, node: str) -> List[str]:
        """Direct causes of this node."""
        return [cause for cause, _ in self.incoming.get(node, [])]

    def children(self, node: str) -> List[str]:
        """Direct effects of this node."""
        return [effect for effect, _ in self.outgoing.get(node, [])]

    def ancestors(self, node: str, max_depth: int = 10) -> Set[str]:
        """All transitive causes (BFS upward)."""
        visited = set()
        queue = [node]
        for _ in range(max_depth):
            if not queue:
                break
            current = queue.pop(0)
            for parent, _ in self.incoming.get(current, []):
                if parent not in visited:
                    visited.add(parent)
                    queue.append(parent)
        return visited

    def descendants(self, node: str, max_depth: int = 10) -> Set[str]:
        """All transitive effects (BFS downward)."""
        visited = set()
        queue = [node]
        for _ in range(max_depth):
            if not queue:
                break
            current = queue.pop(0)
            for child, _ in self.outgoing.get(current, []):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return visited

    def n_nodes(self) -> int:
        return len(self.nodes)

    def n_edges(self) -> int:
        return len(self.edges)


@dataclass
class AbductiveResult:
    """Result of abductive inference: ranked causes for observed effects."""
    cause: str
    cause_type: str        # "domain", "technique", "tool"
    posterior: float       # P(cause | effects)
    prior: float           # P(cause)
    likelihood: float      # P(effects | cause)
    explanation: str = ""
    supporting_rules: List[Dict] = field(default_factory=list)


@dataclass
class Counterfactual:
    """A counterfactual "what-if" scenario."""
    problem_id: str
    original_domain: str
    counterfactual_domain: str
    preserved_features: List[str]   # invariant under domain change
    changed_features: List[Tuple[str, str]]  # (original → counterfactual)
    confidence: float
    interpretation: str = ""


@dataclass
class RootCause:
    """A root cause identified by tracing effects backward."""
    feature: str
    depth: int             # distance from observation
    causal_chain: List[str]  # from root to observation
    strength: float        # product of edge strengths
    evidence: List[str] = field(default_factory=list)


# ─── Causal Graph Construction ─────────────────────────────────────────────────

def build_causal_graph_from_rules(
    rules: List[Any],       # association rules with antecedent/consequent/confidence
    domain_labels: Optional[Dict[str, str]] = None,
) -> CausalGraph:
    """Build causal graph from Apriori association rules.

    Each rule antecedent → consequent is treated as a candidate causal edge
    with strength = confidence. Domain knowledge can override edge direction.
    """
    graph = CausalGraph()

    for rule in rules:
        # Unpack rule (compatible with our Apriori output)
        ante = getattr(rule, 'antecedent', None)
        cons = getattr(rule, 'consequent', None)
        conf = getattr(rule, 'confidence', None)
        supp = getattr(rule, 'support', None)

        if ante is None or cons is None:
            continue

        ante_items = list(ante) if isinstance(ante, (tuple, frozenset, set)) else [str(ante)]
        cons_items = list(cons) if isinstance(cons, (tuple, frozenset, set)) else [str(cons)]
        conf_val = float(conf) if conf else 0.5
        supp_val = float(supp) if supp else 0.0

        # For multi-item rules, create edges from each antecedent to each consequent
        for a_item in ante_items:
            a_str = str(a_item)
            graph.node_types.setdefault(a_str, "feature")
            for c_item in cons_items:
                c_str = str(c_item)
                graph.node_types.setdefault(c_str, "feature")

                # Determine edge type
                etype = "direct"
                rationale = f"Apriori rule: {a_str} → {c_str} (confidence={conf_val:.3f})"

                # Check domain knowledge: if one is a domain label, orient accordingly
                if domain_labels:
                    if a_str in domain_labels:
                        etype = "domain_knowledge"
                        rationale = f"Domain {a_str} causes feature {c_str}"
                    elif c_str in domain_labels:
                        etype = "domain_knowledge"
                        rationale = f"Domain {c_str} causes feature {a_str}"

                edge = CausalEdge(
                    cause=a_str,
                    effect=c_str,
                    strength=conf_val,
                    support=supp_val,
                    edge_type=etype,
                    rationale=rationale,
                )
                graph.add_edge(edge)

    return graph


def build_causal_graph_from_transactions(
    transactions: List[Set[str]],
    domain_per_transaction: Optional[Dict[int, str]] = None,
    min_confidence: float = 0.3,
) -> CausalGraph:
    """Build causal graph from transaction data with domain as root cause.

    Domain → feature edges: P(feature | domain) = support.
    Feature → feature edges: from co-occurrence patterns.
    """
    graph = CausalGraph()

    # Count domains
    domain_counts: Dict[str, int] = defaultdict(int)
    feature_by_domain: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for txn_idx, txn in enumerate(transactions):
        dom = domain_per_transaction.get(txn_idx, "unknown") if domain_per_transaction else "unknown"
        domain_counts[dom] += 1
        for feat in txn:
            feature_by_domain[dom][feat] += 1
            graph.nodes.add(feat)
            graph.node_types.setdefault(feat, "feature")

    total_txns = len(transactions)
    if total_txns == 0:
        return graph

    # Add domain nodes
    for dom in domain_counts:
        graph.nodes.add(dom)
        graph.node_types[dom] = "domain"
        dom_prior = domain_counts[dom] / total_txns

        for feat, count in feature_by_domain[dom].items():
            strength = count / domain_counts[dom]  # P(feat | domain)
            support = count / total_txns
            if strength >= min_confidence:
                edge = CausalEdge(
                    cause=dom, effect=feat,
                    strength=round(strength, 4),
                    support=round(support, 4),
                    edge_type="domain_knowledge",
                    rationale=f"P({feat} | {dom}) = {strength:.3f}",
                )
                graph.add_edge(edge)

    # Feature → feature edges from co-occurrence lift
    all_features = sorted(graph.nodes - set(domain_counts.keys()))
    feat_support: Dict[str, float] = {}
    cooccur: Dict[Tuple[str, str], int] = defaultdict(int)

    for txn in transactions:
        txn_list = sorted(txn)
        for feat in txn_list:
            feat_support[feat] = feat_support.get(feat, 0) + 1
        for a, b in combinations(txn_list, 2):
            if a in all_features and b in all_features:
                cooccur[(a, b)] += 1
                cooccur[(b, a)] += 1

    for a in feat_support:
        p_a = feat_support[a] / total_txns
        if p_a == 0:
            continue
        for b in feat_support:
            if a >= b:
                continue
            p_b = feat_support[b] / total_txns
            if p_b == 0:
                continue
            p_ab = cooccur[(a, b)] / total_txns
            if p_ab == 0:
                continue
            # Forward confidence: a → b
            conf_ab = p_ab / p_a
            # Backward confidence: b → a
            conf_ba = p_ab / p_b
            # Lift
            lift = p_ab / (p_a * p_b) if p_a * p_b > 0 else 0.0

            if conf_ab >= min_confidence and lift > 1.0:
                graph.add_edge(CausalEdge(
                    cause=a, effect=b, strength=round(conf_ab, 4),
                    support=round(p_ab, 4), edge_type="discovered",
                    rationale=f"P({b}|{a})={conf_ab:.3f}, lift={lift:.2f}",
                ))
            if conf_ba >= min_confidence and lift > 1.0:
                graph.add_edge(CausalEdge(
                    cause=b, effect=a, strength=round(conf_ba, 4),
                    support=round(p_ab, 4), edge_type="discovered",
                    rationale=f"P({a}|{b})={conf_ba:.3f}, lift={lift:.2f}",
                ))

    return graph


# ─── Abductive Inference (逆向推理) ─────────────────────────────────────────────

def abductive_inference(
    observed_effects: Set[str],
    graph: CausalGraph,
    candidate_causes: Optional[List[str]] = None,
    top_k: int = 10,
) -> List[AbductiveResult]:
    """Infer most likely causes given observed effects (abduction).

    For each candidate cause C:
      P(C | effects) ∝ P(effects | C) × P(C)

    P(effects | C): product of P(e_i | C) for each observed effect (naive Bayes)
    P(C): prior probability of C (estimated from edge support values)

    Args:
        observed_effects: Set of observed feature names.
        graph: Causal graph with strength = P(effect | cause).
        candidate_causes: Optional list of candidate cause nodes.
                          If None, uses all domain nodes + nodes with outgoing edges.
        top_k: Number of top results to return.

    Returns:
        List of AbductiveResult sorted by posterior descending.
    """
    if not observed_effects:
        return []

    # Determine candidate causes
    if candidate_causes is None:
        # Look for domain nodes and nodes that have causal influence on the effects
        candidate_causes = []
        for node in graph.nodes:
            ntype = graph.node_types.get(node, "")
            if ntype == "domain":
                candidate_causes.append(node)
        # Also include feature nodes that are parents of observed effects
        for effect in observed_effects:
            for parent, _ in graph.incoming.get(effect, []):
                if parent not in candidate_causes:
                    candidate_causes.append(parent)

    if not candidate_causes:
        return []

    # Estimate priors P(C) from outgoing edge supports
    total_cause_strength = 0.0
    cause_prior: Dict[str, float] = {}
    for cause in candidate_causes:
        children = graph.outgoing.get(cause, [])
        if children:
            avg_support = sum(
                graph.edges[ei].support for _, ei in children
            ) / len(children)
        else:
            avg_support = 0.01
        cause_prior[cause] = avg_support
        total_cause_strength += avg_support

    if total_cause_strength == 0:
        return []

    # Normalize priors
    for cause in cause_prior:
        cause_prior[cause] /= total_cause_strength

    # Compute posterior for each candidate cause
    results = []
    for cause in candidate_causes:
        # P(effects | cause): evidence likelihood via causal edges
        log_likelihood = 0.0
        evidence_count = 0
        supporting = []

        for effect in observed_effects:
            # Check if there's a direct causal edge cause → effect
            best_strength = 0.0
            for child, ei in graph.outgoing.get(cause, []):
                if child == effect:
                    edge = graph.edges[ei]
                    best_strength = max(best_strength, edge.strength)
                    supporting.append({
                        "cause": cause, "effect": effect,
                        "strength": edge.strength,
                        "rationale": edge.rationale,
                    })
                    break

            # Also check indirect: cause → intermediate → effect
            if best_strength == 0.0:
                for child, ei1 in graph.outgoing.get(cause, []):
                    for grandchild, ei2 in graph.outgoing.get(child, []):
                        if grandchild == effect:
                            e1 = graph.edges[ei1]
                            e2 = graph.edges[ei2]
                            chain_strength = e1.strength * e2.strength
                            best_strength = max(best_strength, chain_strength)
                            break

            if best_strength > 0.0:
                log_likelihood += math.log(max(best_strength, 1e-10))
                evidence_count += 1
            else:
                # Penalty for unexplained effects
                log_likelihood += math.log(0.01)

        likelihood = math.exp(log_likelihood) if evidence_count > 0 else 1e-10
        prior = cause_prior.get(cause, 0.01)
        posterior = likelihood * prior  # unnormalized

        ntype = graph.node_types.get(cause, "feature")
        results.append(AbductiveResult(
            cause=cause,
            cause_type=ntype,
            posterior=round(posterior, 6),
            prior=round(prior, 4),
            likelihood=round(likelihood, 6),
            explanation=_build_abductive_explanation(
                cause, observed_effects, evidence_count, graph
            ),
            supporting_rules=supporting,
        ))

    # Normalize posteriors
    total_post = sum(r.posterior for r in results)
    if total_post > 0:
        for r in results:
            r.posterior = round(r.posterior / total_post, 4)

    results.sort(key=lambda r: -r.posterior)
    return results[:top_k]


def _build_abductive_explanation(
    cause: str, effects: Set[str], evidence_count: int, graph: CausalGraph,
) -> str:
    """Build a natural-language explanation for an abductive result."""
    if evidence_count == 0:
        return f"{cause} 不能解释任何观察到的效应 — 可能性极低"

    ratio = evidence_count / len(effects)
    if ratio >= 0.8:
        return f"{cause} 能解释 {evidence_count}/{len(effects)} 个观察效应 — 高度可能"
    elif ratio >= 0.5:
        return f"{cause} 能解释 {evidence_count}/{len(effects)} 个观察效应 — 中等可能"
    else:
        return f"{cause} 只能解释 {evidence_count}/{len(effects)} 个观察效应 — 低可能"


def infer_problem_domain(
    observed_tools: Set[str],
    graph: CausalGraph,
) -> List[AbductiveResult]:
    """Convenience: infer most likely problem domain from observed tools.

    This is the core "逆向思维" operation: you see what tools were used,
    and reason backwards to what type of problem it must have been.
    """
    domain_causes = [
        node for node in graph.nodes
        if graph.node_types.get(node) == "domain"
    ]
    return abductive_inference(
        observed_tools, graph,
        candidate_causes=domain_causes if domain_causes else None,
    )


# ─── Counterfactual Reasoning ──────────────────────────────────────────────────

def counterfactual_domain_change(
    problem_id: str,
    source_features: Set[str],
    source_domain: str,
    target_domain: str,
    isomorphisms: List[Any],   # IsomorphismMapping objects
    profiles: List[Any],       # InvariantProfile objects
) -> Counterfactual:
    """Reason counterfactually: "If this problem were in domain D' instead of D..."

    Uses isomorphism feature_mapping to transform features across domains.
    Features with no mapping are preserved (invariant to domain change).
    """
    # Find best isomorphism between source and target domain
    best_iso = None
    best_score = 0.0
    for iso in isomorphisms:
        if not hasattr(iso, 'source_domain') or not hasattr(iso, 'target_domain'):
            continue
        if ((iso.source_domain == source_domain and iso.target_domain == target_domain) or
            (iso.source_domain == target_domain and iso.target_domain == source_domain)):
            if iso.score > best_score:
                best_score = iso.score
                best_iso = iso

    mapping: Dict[str, str] = {}
    if best_iso and hasattr(best_iso, 'feature_mapping'):
        raw_mapping = best_iso.feature_mapping
        if best_iso.source_domain == source_domain:
            mapping = dict(raw_mapping)
        else:
            mapping = {v: k for k, v in raw_mapping.items()}

    # Classify features
    preserved = []
    changed = []

    for feat in sorted(source_features):
        if feat in mapping:
            changed.append((feat, mapping[feat]))
        else:
            preserved.append(feat)

    # Confidence based on isomorphism score and mapping coverage
    mapped_ratio = len(changed) / max(1, len(source_features))
    confidence = best_score * 0.6 + mapped_ratio * 0.4

    return Counterfactual(
        problem_id=problem_id,
        original_domain=source_domain,
        counterfactual_domain=target_domain,
        preserved_features=preserved,
        changed_features=changed,
        confidence=round(confidence, 4),
        interpretation=_build_counterfactual_interpretation(
            preserved, changed, source_domain, target_domain, confidence
        ),
    )


def _build_counterfactual_interpretation(
    preserved: List[str], changed: List[Tuple[str, str]],
    src: str, tgt: str, conf: float,
) -> str:
    n_preserved = len(preserved)
    n_changed = len(changed)
    if n_changed == 0:
        return f"从 {src} 迁移到 {tgt} 时无可映射特征 — 两域结构差异大，反事实推理置信度低"
    if conf > 0.7:
        return (f"若在 {tgt} 域, {n_changed} 个特征将变换 ({n_preserved} 个保留)。"
                f"强同构支持高置信度跨域推理。")
    return (f"若在 {tgt} 域, {n_changed} 个特征将变换 ({n_preserved} 个不变)。"
            f"同构度中等，反事实推断仅供参考。")


# ─── Causal Discovery (Simplified PC) ──────────────────────────────────────────

def causal_discovery(
    transactions: List[Set[str]],
    min_dependency: float = 0.1,
    max_condition_set: int = 2,
) -> CausalGraph:
    """Simplified constraint-based causal discovery from transaction data.

    Phase 1: Build skeleton (undirected edges) via pairwise dependency tests.
    Phase 2: Orient edges using v-structure detection and domain knowledge.

    Uses mutual information / lift as dependency measure.
    """
    graph = CausalGraph()

    all_items = sorted(set().union(*transactions))
    n = len(transactions)
    item_to_idx = {item: i for i, item in enumerate(all_items)}

    for item in all_items:
        graph.nodes.add(item)
        graph.node_types[item] = "feature"

    # Phase 1: skeleton — test all pairs for marginal dependence
    skeleton: Dict[Tuple[str, str], float] = {}  # (a,b) → dependency score
    item_support: Dict[str, int] = defaultdict(int)
    cooccur: Dict[Tuple[str, str], int] = defaultdict(int)

    for txn in transactions:
        txn_list = sorted(txn)
        for feat in txn_list:
            item_support[feat] += 1
        for a, b in combinations(txn_list, 2):
            cooccur[(a, b)] += 1
            cooccur[(b, a)] += 1

    for a, b in combinations(all_items, 2):
        p_a = item_support[a] / n
        p_b = item_support[b] / n
        p_ab = cooccur[(a, b)] / n
        if p_a == 0 or p_b == 0:
            continue

        # Lift as dependency measure
        lift = p_ab / (p_a * p_b) if p_a * p_b > 0 else 0.0
        # Also compute conditional: P(a|b) and P(b|a)
        conf_ab = p_ab / p_b if p_b > 0 else 0.0
        conf_ba = p_ab / p_a if p_a > 0 else 0.0

        dependency = max(lift - 1.0, 0.0)  # lift > 1 means positive dependence
        if dependency >= min_dependency:
            skeleton[(a, b)] = dependency
            skeleton[(b, a)] = dependency

    # Phase 2: orient edges — keep the stronger causal direction
    # For each skeleton edge, determine direction by comparing P(a|b) vs P(b|a)
    oriented = set()
    for (a, b), dep in sorted(skeleton.items(), key=lambda x: -x[1]):
        if (a, b) in oriented or (b, a) in oriented:
            continue

        p_a = item_support[a] / n
        p_b = item_support[b] / n
        p_ab = cooccur[(a, b)] / n
        conf_ab = p_ab / p_b if p_b > 0 else 0.0
        conf_ba = p_ab / p_a if p_a > 0 else 0.0

        # Orient: the rarer item → the more common item (common effect)
        # This follows from the causal principle that causes tend to be more general
        # and effects more specific (domain → tool, technique → tool)
        if p_a < p_b and conf_ab > conf_ba:
            graph.add_edge(CausalEdge(
                cause=a, effect=b, strength=round(conf_ba, 4),
                support=round(p_ab, 4), edge_type="discovered",
                rationale=f"Discovered: P({b}|{a})={conf_ba:.3f}, lift={dep+1:.2f}",
            ))
            oriented.add((a, b))
        elif p_b < p_a and conf_ba > conf_ab:
            graph.add_edge(CausalEdge(
                cause=b, effect=a, strength=round(conf_ab, 4),
                support=round(p_ab, 4), edge_type="discovered",
                rationale=f"Discovered: P({a}|{b})={conf_ab:.3f}, lift={dep+1:.2f}",
            ))
            oriented.add((b, a))
        elif conf_ab >= conf_ba:
            graph.add_edge(CausalEdge(
                cause=b, effect=a, strength=round(conf_ab, 4),
                support=round(p_ab, 4), edge_type="discovered",
            ))
            oriented.add((b, a))
        else:
            graph.add_edge(CausalEdge(
                cause=a, effect=b, strength=round(conf_ba, 4),
                support=round(p_ab, 4), edge_type="discovered",
            ))
            oriented.add((a, b))

    return graph


# ─── Root Cause Tracing ────────────────────────────────────────────────────────

def find_root_causes(
    observed_feature: str,
    graph: CausalGraph,
    max_depth: int = 5,
) -> List[RootCause]:
    """Trace an observed feature back to its root causes.

    BFS upward through the causal graph until reaching nodes with no parents
    (root causes). Returns all root cause chains with strengths.
    """
    roots = []
    visited_chains = set()

    def dfs(node: str, chain: List[str], strength: float, depth: int):
        if depth > max_depth:
            return
        parents = graph.parents(node)
        if not parents:
            chain_key = tuple(chain)
            if chain_key not in visited_chains:
                visited_chains.add(chain_key)
                roots.append(RootCause(
                    feature=node,
                    depth=depth,
                    causal_chain=list(chain) + [node],
                    strength=round(strength, 6),
                ))
            return

        for parent, ei in graph.incoming.get(node, []):
            edge = graph.edges[ei]
            new_strength = strength * edge.strength
            dfs(parent, chain + [node], new_strength, depth + 1)

    dfs(observed_feature, [], 1.0, 0)

    # Deduplicate: keep shortest chain per root feature
    best = {}
    for r in roots:
        if r.feature not in best or r.depth < best[r.feature].depth:
            best[r.feature] = r

    result = sorted(best.values(), key=lambda r: -r.strength)
    return result


def estimate_intervention_effect(
    intervention: str,        # feature to intervene on (set to present)
    target: str,              # feature whose change we want to predict
    graph: CausalGraph,
) -> Dict[str, Any]:
    """Estimate the effect of intervening on a feature.

    P(target | do(intervention=1)) ≈ sum over parents of target:
      P(target | intervention, other_parents) × P(other_parents)

    Simplified: use the causal edge strength as effect estimate.
    """
    # Check direct effect
    direct_effect = 0.0
    for child, ei in graph.outgoing.get(intervention, []):
        if child == target:
            direct_effect = graph.edges[ei].strength
            break

    # Check indirect effects (2-hop)
    indirect_effects = []
    for child, ei1 in graph.outgoing.get(intervention, []):
        for grandchild, ei2 in graph.outgoing.get(child, []):
            if grandchild == target:
                e1 = graph.edges[ei1]
                e2 = graph.edges[ei2]
                chain_strength = e1.strength * e2.strength
                indirect_effects.append({
                    "mediator": child,
                    "strength": round(chain_strength, 4),
                    "chain": f"{intervention} → {child} → {target}",
                })

    total_effect = direct_effect
    for ie in indirect_effects:
        total_effect = 1.0 - (1.0 - total_effect) * (1.0 - ie["strength"])

    return {
        "intervention": intervention,
        "target": target,
        "direct_effect": round(direct_effect, 4),
        "indirect_effects": indirect_effects,
        "total_effect": round(total_effect, 4),
        "interpretation": (
            f"干预 {intervention} 对 {target} 有显著因果效应"
            if total_effect > 0.5 else
            f"干预 {intervention} 对 {target} 有中等因果效应"
            if total_effect > 0.2 else
            f"干预 {intervention} 对 {target} 因果效应较弱"
        ),
    }


# ─── Formatters ────────────────────────────────────────────────────────────────


def format_causal_graph_summary(graph: CausalGraph) -> str:
    """Format causal graph summary."""
    lines = [
        "# 因果图摘要",
        "",
        f"- **节点数**: {graph.n_nodes()}",
        f"- **边数**: {graph.n_edges()}",
        "",
    ]

    # Node type distribution
    ntype_counts: Dict[str, int] = defaultdict(int)
    for node in graph.nodes:
        ntype = graph.node_types.get(node, "feature")
        ntype_counts[ntype] += 1
    lines.append("### 节点类型分布")
    for ntype, count in sorted(ntype_counts.items()):
        lines.append(f"- {ntype}: {count}")
    lines.append("")

    # Top edges by strength
    if graph.edges:
        lines.append("### 最强因果边")
        lines.append("")
        lines.append("| 原因 | 结果 | 强度 | 类型 | 依据 |")
        lines.append("|------|------|------|------|------|")
        top_edges = sorted(graph.edges, key=lambda e: -e.strength)[:15]
        for edge in top_edges:
            rationale = edge.rationale[:60] + "..." if len(edge.rationale) > 60 else edge.rationale
            lines.append(
                f"| `{edge.cause}` | `{edge.effect}` "
                f"| {edge.strength:.3f} | {edge.edge_type} | {rationale} |"
            )
        lines.append("")

    # Root nodes (no parents)
    roots = [n for n in graph.nodes if not graph.parents(n)]
    lines.append(f"### 根因节点 (无父节点): {len(roots)}")
    for r in sorted(roots)[:10]:
        n_children = len(graph.children(r))
        lines.append(f"  - `{r}` → {n_children} 个子节点")
    lines.append("")

    # Leaf nodes (no children)
    leaves = [n for n in graph.nodes if not graph.children(n)]
    lines.append(f"### 叶节点 (无子节点): {len(leaves)}")
    lines.append(f"  {', '.join(f'`{l}`' for l in sorted(leaves)[:12])}")
    lines.append("")

    return "\n".join(lines)


def format_abductive_results(
    results: List[AbductiveResult],
    observed: Set[str],
) -> str:
    """Format abductive inference results."""
    lines = [
        "# 逆向推理结果 (Abductive Inference)",
        "",
        f"**观察到的效应**: {', '.join(f'`{e}`' for e in sorted(observed))}",
        "",
    ]

    if not results:
        lines.append("未找到可能的原因。")
        return "\n".join(lines)

    lines.append("| 排名 | 原因 | 类型 | 后验概率 | 先验 | 似然 | 解释 |")
    lines.append("|------|------|------|----------|------|------|------|")
    for rank, r in enumerate(results, 1):
        lines.append(
            f"| {rank} | `{r.cause}` | {r.cause_type} "
            f"| {r.posterior:.4f} | {r.prior:.4f} | {r.likelihood:.6f} "
            f"| {r.explanation} |"
        )
    lines.append("")

    # Supporting rules for top result
    if results and results[0].supporting_rules:
        lines.append("### 最佳推断的支持规则")
        lines.append("")
        for rule in results[0].supporting_rules:
            lines.append(
                f"- `{rule['cause']}` → `{rule['effect']}` "
                f"(强度={rule['strength']:.3f}): {rule['rationale']}"
            )
        lines.append("")

    return "\n".join(lines)


def format_counterfactual(cf: Counterfactual) -> str:
    """Format a counterfactual scenario."""
    lines = [
        "# 反事实推理 (Counterfactual)",
        "",
        f"**问题**: `{cf.problem_id}`",
        f"**原域**: {cf.original_domain} → **假设域**: {cf.counterfactual_domain}",
        f"**置信度**: {cf.confidence:.4f}",
        "",
        f"**解读**: {cf.interpretation}",
        "",
    ]

    if cf.preserved_features:
        lines.append("### 保留特征 (域不变)")
        for feat in sorted(cf.preserved_features)[:15]:
            lines.append(f"  - `{feat}`")
        if len(cf.preserved_features) > 15:
            lines.append(f"  ... 另有 {len(cf.preserved_features) - 15} 个")
        lines.append("")

    if cf.changed_features:
        lines.append("### 变换特征 (域相关)")
        lines.append("")
        lines.append("| 原特征 | 反事实特征 |")
        lines.append("|--------|------------|")
        for orig, cf_feat in cf.changed_features[:12]:
            lines.append(f"| `{orig}` | `{cf_feat}` |")
        if len(cf.changed_features) > 12:
            lines.append(f"| ... | ... +{len(cf.changed_features) - 12} 对 |")
        lines.append("")

    return "\n".join(lines)


def format_root_causes(
    root_causes: List[RootCause],
    observed: str,
) -> str:
    """Format root cause analysis."""
    lines = [
        "# 根因分析 (Root Cause Tracing)",
        "",
        f"**观察特征**: `{observed}`",
        f"**根因数**: {len(root_causes)}",
        "",
    ]

    if not root_causes:
        lines.append("未找到根因 — 此特征可能在因果图中为根节点。")
        return "\n".join(lines)

    lines.append("| 根因 | 深度 | 因果链 | 强度 |")
    lines.append("|------|------|--------|------|")
    for rc in root_causes[:15]:
        chain_str = " → ".join(f"`{n}`" for n in rc.causal_chain)
        lines.append(
            f"| `{rc.feature}` | {rc.depth} | {chain_str} | {rc.strength:.4f} |"
        )
    lines.append("")

    return "\n".join(lines)


def format_intervention_effect(result: Dict[str, Any]) -> str:
    """Format intervention effect estimation."""
    lines = [
        "# 干预效应估计",
        "",
        f"**干预**: do(`{result['intervention']}` = 1)",
        f"**目标**: `{result['target']}`",
        f"**直接效应**: {result['direct_effect']:.4f}",
        f"**总效应**: {result['total_effect']:.4f}",
        f"**解读**: {result['interpretation']}",
        "",
    ]

    if result["indirect_effects"]:
        lines.append("### 间接路径")
        for ie in result["indirect_effects"]:
            lines.append(f"- 通过 `{ie['mediator']}`: {ie['strength']:.4f} ({ie['chain']})")
        lines.append("")

    return "\n".join(lines)
