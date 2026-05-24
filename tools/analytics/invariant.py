"""Problem Invariant Extraction — 题目不变量提取 / 题目本质识别.

Fuses group theory (permutation groups, symmetry, orbit decomposition) with
Apriori frequent pattern mining to identify the invariant core of CTF problems.

Core insight:
  - Apriori finds FREQUENT feature patterns across problem instances
  - Group theory identifies which patterns are INVARIANT under transformations
  - The intersection = problem ESSENCE (题目本质): what stays constant across
    all valid variations of a problem type

Algorithm pipeline:
  1. Apriori → candidate invariant itemsets (frequent + closed)
  2. Group theory → define transformation group on feature space
  3. Orbit decomposition → partition features by invariance
  4. Filter → keep itemsets with high invariance score
  5. Essence → organize into core/structural/accidental tiers

Mathematical foundation:
  - G = transformation group acting on feature space F
  - Orb_G(S) = {g(S) | g ∈ G}  — orbit of itemset S
  - inv_deg(S) = 1 / |Orb_G(S)|  — invariance degree
  - essence(P) = {S : support(S) ≥ min_sup AND inv_deg(S) ≥ min_inv}
"""

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Dict, List, Set, Tuple, FrozenSet, Optional, Callable, Any
import math


# ─── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class FeatureSpace:
    """The space of all possible problem features.

    Each feature is an atomic label: a tag, tool name, technique, or
    mathematical structure that can appear in a problem description.
    """
    features: List[str] = field(default_factory=list)
    feature_to_idx: Dict[str, int] = field(default_factory=dict)
    domains: Dict[str, str] = field(default_factory=dict)  # feature → domain

    def __post_init__(self):
        if self.features and not self.feature_to_idx:
            self.feature_to_idx = {f: i for i, f in enumerate(self.features)}

    def add_feature(self, name: str, domain: str = "") -> int:
        if name not in self.feature_to_idx:
            idx = len(self.features)
            self.features.append(name)
            self.feature_to_idx[name] = idx
            if domain:
                self.domains[name] = domain
            return idx
        return self.feature_to_idx[name]

    def get_idx(self, name: str) -> Optional[int]:
        return self.feature_to_idx.get(name)

    def __len__(self) -> int:
        return len(self.features)

    def __contains__(self, name: str) -> bool:
        return name in self.feature_to_idx


@dataclass
class ProblemSignature:
    """A concrete problem's feature signature.

    Each problem is represented as a set of features drawn from the
    feature space. This is the input to both Apriori and group-theoretic
    analysis.
    """
    problem_id: str
    features: Set[str]
    domain: str = ""
    difficulty: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def feature_indices(self, space: FeatureSpace) -> Set[int]:
        return {space.feature_to_idx[f] for f in self.features if f in space}

    def __hash__(self) -> int:
        return hash(self.problem_id)

    def __eq__(self, other) -> bool:
        return isinstance(other, ProblemSignature) and self.problem_id == other.problem_id


@dataclass
class Permutation:
    """A permutation on feature indices.

    Represents a transformation of the feature space. For example,
    'vol3' → 'volatility' is a permutation that swaps two feature indices
    and fixes all others.

    Stored in cycle notation for efficiency with sparse permutations.
    """
    mapping: Dict[int, int] = field(default_factory=dict)

    def apply_to_idx(self, idx: int) -> int:
        return self.mapping.get(idx, idx)

    def apply_to_set(self, indices: Set[int]) -> FrozenSet[int]:
        return frozenset(self.apply_to_idx(i) for i in indices)

    def apply_to_items(self, items: FrozenSet[str], space: FeatureSpace) -> FrozenSet[str]:
        result = set()
        for item in items:
            if item in space:
                orig_idx = space.feature_to_idx[item]
                new_idx = self.apply_to_idx(orig_idx)
                result.add(space.features[new_idx])
            else:
                result.add(item)
        return frozenset(result)

    def compose(self, other: "Permutation") -> "Permutation":
        """self ∘ other: apply other first, then self."""
        composed = {}
        all_keys = set(self.mapping.keys()) | set(other.mapping.keys())
        for k in all_keys:
            v = other.apply_to_idx(k)
            v = self.apply_to_idx(v)
            if v != k:
                composed[k] = v
        return Permutation(composed)

    def inverse(self) -> "Permutation":
        inv = {v: k for k, v in self.mapping.items()}
        return Permutation(inv)

    def __repr__(self) -> str:
        cycles = self._to_cycles()
        if not cycles:
            return "id"
        return " ∘ ".join(
            "(" + " → ".join(str(c) for c in cycle) + ")" for cycle in cycles
        )

    def _to_cycles(self) -> List[List[int]]:
        visited = set()
        cycles = []
        for k in sorted(self.mapping.keys()):
            if k in visited:
                continue
            cycle = []
            cur = k
            while cur not in visited:
                visited.add(cur)
                cycle.append(cur)
                cur = self.mapping.get(cur, cur)
            if len(cycle) > 1:
                cycles.append(cycle)
        return cycles


@dataclass
class TransformationRule:
    """A human-readable rule that generates permutations.

    Examples:
      - "tool_version_normalize": {python3, python, python310} → python
      - "encoding_variant": {base64, hex, raw} all equivalent for this purpose
      - "rsa_keysize": {rsa_1024, rsa_2048, rsa_4096} → rsa (same essence)
    """
    name: str
    description: str
    feature_group: List[str]  # features that are equivalent under this rule
    domain: str = ""          # which problem domain this rule applies to


@dataclass
class PermutationGroup:
    """A group of permutations on the feature space.

    Defined by a set of generators. The group is the closure of these
    generators under composition. The full group may be very large;
    we compute orbits without enumerating all elements.
    """
    generators: List[Permutation] = field(default_factory=list)
    _space: Optional[FeatureSpace] = None

    def act_on_set(self, items: FrozenSet[str], space: FeatureSpace) -> Set[FrozenSet[str]]:
        """Compute orbit of an itemset under the group action (BFS on generators)."""
        seen = {items}
        queue = [items]
        for current in queue:
            for gen in self.generators:
                neighbor = gen.apply_to_items(current, space)
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return seen

    def orbit_size(self, items: FrozenSet[str], space: FeatureSpace) -> int:
        return len(self.act_on_set(items, space))

    def is_invariant(self, items: FrozenSet[str], space: FeatureSpace) -> bool:
        """An itemset is fully invariant if every generator fixes it."""
        for gen in self.generators:
            if gen.apply_to_items(items, space) != items:
                return False
        return True

    def partial_invariance(self, items: FrozenSet[str], space: FeatureSpace) -> float:
        """Fraction of generators that fix this itemset. 1.0 = fully invariant."""
        if not self.generators:
            return 1.0
        fixed = sum(
            1 for g in self.generators if g.apply_to_items(items, space) == items
        )
        return fixed / len(self.generators)

    def add_generator(self, perm: Permutation):
        self.generators.append(perm)

    def add_transposition(self, i: int, j: int):
        """Add a transposition (swap) between two feature indices."""
        m = {i: j, j: i}
        self.generators.append(Permutation(m))

    def n_generators(self) -> int:
        return len(self.generators)


# ─── Schreier-Sims Algorithm ──────────────────────────────────────────────────

@dataclass
class SchreierSimsResult:
    """Output of Schreier-Sims: base B and strong generating set S.

    B = [β₁, ..., βₖ]: a base — pointwise stabilizer chain descends to {id}
    S = [S₁, ..., Sₖ]: strong generators — Sᵢ generates G⁽ⁱ⁾ = stabilizer of
        {β₁, ..., βᵢ₋₁} restricted to the stabilizer of βᵢ

    Complexity: O(n²|S| + n|S|²) for n points and |S| strong generators.

    Usage:
      result = schreier_sims(group, n_points=len(feature_space))
      result.order         # |G| — total number of group elements
      result.member(g)     # is permutation g in the group?
      result.base          # base points
    """
    base: List[int] = field(default_factory=list)
    strong_generators: List[List[Permutation]] = field(default_factory=list)
    group_order: int = 1

    def member(self, g: Permutation) -> bool:
        """Test membership: is permutation g in the group?

        Uses the sift procedure: for each base point βᵢ, apply g to βᵢ and
        traverse the Schreier tree to see if the result is in the orbit.
        """
        for i, beta in enumerate(self.base):
            beta_img = g.apply_to_idx(beta)
            if beta_img == beta:
                continue
            # Try to find a generator that maps beta → beta_img
            found = False
            for s in self.strong_generators[i]:
                if s.apply_to_idx(beta) == beta_img:
                    g = g.compose(s.inverse())
                    found = True
                    break
            if not found:
                return False
        # After sifting through all levels, g should be identity
        return len(g.mapping) == 0

    def summary(self) -> str:
        lines = [
            f"Schreier-Sims Result:",
            f"  Base: {self.base}",
            f"  |G| = {self.group_order:,}",
        ]
        for i, sg in enumerate(self.strong_generators):
            lines.append(f"  S{i} = {len(sg)} generators (stabilizer of {self.base[:i]})")
        return "\n".join(lines)


def schreier_sims(group: PermutationGroup, n_points: int) -> SchreierSimsResult:
    """Compute base and strong generating set for a permutation group.

    Deterministic Schreier-Sims variant using Schreier's lemma.

    Algorithm:
      1. Choose β = next unused point as new base point.
      2. Compute orbit Δ of β under current stabilizer generators S.
      3. Build Schreier tree: for each δ ∈ Δ, record u_δ with u_δ(β) = δ.
      4. Schreier generators: for each δ ∈ Δ, g ∈ S, h = u_{g(δ)}^{−1} ∘ g ∘ u_δ.
         These generate Stab_G(β).
      5. Repeat with new generators until stabilizer is trivial.

    Reference: Seress, "Permutation Group Algorithms" (2003), Ch. 4.
    """
    if n_points == 0:
        return SchreierSimsResult()

    generators = [Permutation(dict(g.mapping)) for g in group.generators]
    if not generators:
        return SchreierSimsResult(base=[],
                                  strong_generators=[[]],
                                  group_order=1)

    base: List[int] = []
    strong: List[List[Permutation]] = []
    orders: List[int] = []  # orbit size at each level for order computation

    # S[0] = generators of G (stabilizer of nothing)
    S = [Permutation(dict(g.mapping)) for g in generators]
    strong.append(list(S))

    for beta in range(n_points):
        if beta in base:
            continue

        base.append(beta)

        # Compute orbit of beta under S and build Schreier tree
        orbit: List[int] = [beta]
        orbit_set: Set[int] = {beta}
        tree: Dict[int, Tuple[int, int]] = {beta: (-1, -1)}  # node → (parent, gen_idx)
        queue = [beta]
        while queue:
            x = queue.pop(0)
            for gi, g in enumerate(S):
                y = g.apply_to_idx(x)
                if y not in orbit_set:
                    orbit_set.add(y)
                    orbit.append(y)
                    tree[y] = (x, gi)
                    queue.append(y)

        orders.append(len(orbit_set))

        # Build transversal u_δ: u_δ(β) = δ for each δ in orbit
        # u_δ = g_{i_k} ∘ ... ∘ g_{i_1} where the path from β to δ in tree
        transversal: Dict[int, Permutation] = {}
        for delta in orbit:
            if delta == beta:
                transversal[delta] = Permutation({})
            else:
                # Walk up tree: beta → ... → parent → delta
                path_gens: List[Permutation] = []
                cur = delta
                while cur != beta:
                    parent, gen_idx = tree[cur]
                    path_gens.append(S[gen_idx])
                    cur = parent
                # Compose: apply generator for last step first, etc.
                u = Permutation({})
                for g in reversed(path_gens):
                    u = u.compose(g)
                transversal[delta] = u

        # Schreier's lemma: generators for Stab_G(β)
        # For each δ ∈ orbit, g ∈ S: h = u_{g(δ)}^{−1} ∘ g ∘ u_δ fixes β
        new_S: List[Permutation] = []
        seen_new: Set[FrozenSet[Tuple[int, int]]] = set()

        for delta in orbit:
            u_delta = transversal[delta]
            for g in S:
                g_delta = g.apply_to_idx(delta)
                if g_delta not in transversal:
                    continue
                u_gdelta = transversal[g_delta]
                u_gdelta_inv = u_gdelta.inverse()
                h = u_gdelta_inv.compose(g).compose(u_delta)

                # h should fix beta — verify and clean
                if h.apply_to_idx(beta) != beta:
                    continue

                # Remove beta from mapping to get a clean stabilizer element
                clean_map = {}
                for k, v in h.mapping.items():
                    if k != beta and v != k:
                        clean_map[k] = v
                if clean_map:
                    key = frozenset(clean_map.items())
                    if key not in seen_new:
                        seen_new.add(key)
                        new_S.append(Permutation(clean_map))

        if not new_S:
            # Stabilizer is trivial — no more levels needed
            strong.append([])
            break

        strong.append(list(new_S))
        S = new_S

    # Compute group order: product of orbit sizes at each level
    order = 1
    for sz in orders:
        order *= sz
    # If there were more levels implied by base than orbits computed, pad with 1
    if len(orders) < len(base):
        order *= 1  # trivial stabilizer at deeper levels

    return SchreierSimsResult(base=base, strong_generators=strong, group_order=order)


def _reduce_generators(gens: List[Permutation]) -> List[Permutation]:
    """Remove redundant generators (those that are products of others)."""
    if len(gens) <= 1:
        return gens
    # Keep unique generators by their mapping dict
    seen: Set[FrozenSet[Tuple[int, int]]] = set()
    result = []
    for g in gens:
        key = frozenset(g.mapping.items())
        if key not in seen and g.mapping:
            seen.add(key)
            result.append(g)
    return result


# ─── Conjugacy Classes ────────────────────────────────────────────────────────

@dataclass
class ConjugacyClass:
    """A conjugacy class: {g⁻¹hg | g ∈ G} for a representative h.

    Two transformations are conjugate iff they represent the "same type"
    of feature mapping, just applied at different positions.
    """
    representative: Permutation
    members: List[Permutation] = field(default_factory=list)
    cycle_type: Tuple[int, ...] = field(default_factory=tuple)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def description(self) -> str:
        ct = self.cycle_type
        if not ct:
            return "identity"
        if len(ct) == 1 and ct[0] == 2:
            return "swap (transposition)"
        parts = []
        for c in ct:
            if c == 2:
                parts.append("swap")
            elif c == 3:
                parts.append("3-cycle")
            else:
                parts.append(f"{c}-cycle")
        return " × ".join(parts)


@dataclass
class ConjugacyReport:
    """Full conjugacy class decomposition of a permutation group."""
    classes: List[ConjugacyClass] = field(default_factory=list)
    total_elements: int = 0

    def summary(self) -> str:
        lines = [
            f"Conjugacy Class Decomposition: {len(self.classes)} classes, "
            f"{self.total_elements} non-identity generators",
        ]
        for i, cc in enumerate(self.classes):
            lines.append(
                f"  Class {i+1}: {cc.description} "
                f"(size={cc.size}, {cc.size/self.total_elements*100:.0f}%)"
            )
        return "\n".join(lines)


def compute_conjugacy_classes(
    group: PermutationGroup, n_points: int,
) -> ConjugacyReport:
    """Decompose group generators into conjugacy classes.

    Two permutations σ, τ ∈ S_n are conjugate iff they have the same
    cycle type (same multiset of cycle lengths). This is a complete
    classification: cycle type determines conjugacy class uniquely in S_n.

    However, within a subgroup G < S_n, two elements may have the same
    cycle type but NOT be conjugate in G. This implementation detects
    G-conjugacy via orbit computation under the conjugation action.

    Returns a ConjugacyReport with each class labeled by its cycle type.
    """
    elements = [Permutation(dict(g.mapping)) for g in group.generators]
    if not elements:
        return ConjugacyReport()

    n = len(elements)

    def cycle_type(p: Permutation) -> Tuple[int, ...]:
        """Extract cycle type (sorted cycle lengths) from a permutation."""
        visited: Set[int] = set()
        lengths = []
        for start in p.mapping:
            if start in visited:
                continue
            length = 0
            cur = start
            while cur not in visited:
                visited.add(cur)
                cur = p.apply_to_idx(cur)
                length += 1
            if length > 1:
                lengths.append(length)
        # Also check points mapped to themselves (1-cycles, skipped for compactness)
        return tuple(sorted(lengths))

    # Group by cycle type first (S_n conjugacy)
    by_cycle_type: Dict[Tuple[int, ...], List[Permutation]] = defaultdict(list)
    for g in elements:
        ct = cycle_type(g)
        by_cycle_type[ct].append(g)

    # For each cycle type group, split into G-conjugacy classes
    classes = []
    for ct, members in by_cycle_type.items():
        remaining = list(members)
        while remaining:
            rep = remaining[0]
            g_class = [rep]
            remaining = remaining[1:]

            # Compute G-conjugates of rep
            orbit: Set[FrozenSet[Tuple[int, int]]] = set()
            orbit.add(frozenset(rep.mapping.items()))

            queue = [rep]
            for current in queue:
                for g in elements:
                    conjugate = g.inverse().compose(current).compose(g)
                    key = frozenset(conjugate.mapping.items())
                    if key not in orbit:
                        orbit.add(key)
                        queue.append(conjugate)
                        # Check if any remaining member is this conjugate
                        for i in range(len(remaining) - 1, -1, -1):
                            if frozenset(remaining[i].mapping.items()) == key:
                                g_class.append(remaining[i])
                                remaining.pop(i)

            classes.append(ConjugacyClass(
                representative=rep, members=g_class, cycle_type=ct,
            ))

    # Sort classes by size descending
    classes.sort(key=lambda c: c.size, reverse=True)

    return ConjugacyReport(classes=classes, total_elements=n)


# ─── Character Theory (lightweight) ───────────────────────────────────────────

@dataclass
class CharacterTable:
    """Character table of a permutation representation.

    For a group G acting on feature space V (dim = n_features), the
    character χ(g) = Tr(ρ(g)) = number of fixed points of permutation g.

    This is a single representation's character (the permutation
    representation), not the full irreducible character table.
    """
    group_description: str = ""
    n_features: int = 0
    generators: List[Permutation] = field(default_factory=list)
    characters: Dict[int, int] = field(default_factory=dict)  # gen_idx → χ(gen)

    def compute_character(self, g: Permutation) -> int:
        """Character of permutation representation: fixed points of g."""
        fixed = self.n_features
        for k in g.mapping:
            if g.mapping[k] != k:
                # A point in the mapping domain, not fixed
                fixed -= 1
        # Also account for points not in mapping (fixed by definition)
        n_mapped = len(g.mapping)
        n_unmapped = self.n_features - n_mapped
        # All unmapped points are fixed
        # For mapped points, fixed -= 1 for each non-fixed point
        for k, v in g.mapping.items():
            if k == v:
                fixed += 0  # already counted in unmapped if k not in mapping domain
        # Simpler: count fixed points directly
        fixed_count = 0
        for i in range(self.n_features):
            if g.apply_to_idx(i) == i:
                fixed_count += 1
        return fixed_count

    def build(self):
        """Compute characters for all generators."""
        self.characters = {
            i: self.compute_character(g)
            for i, g in enumerate(self.generators)
        }
        return self

    def inner_product(self, chi1: Callable, chi2: Callable) -> float:
        """Inner product of class functions: ⟨χ₁, χ₂⟩ = 1/|G| Σ_g χ₁(g)χ₂(g).

        For the permutation character, this approximates the decomposition
        into irreducibles: ⟨χ, χ⟩ = number of irreducible components.
        """
        if not self.generators:
            return 0.0
        total = 0.0
        for g in self.generators:
            total += chi1(g) * chi2(g)
        return total / len(self.generators)

    def multiplicity_of_trivial(self) -> float:
        """Multiplicity of the trivial representation in χ.

        ⟨χ, 1⟩ = 1/|G| Σ_g χ(g) = average number of fixed points.
        This equals the number of orbits (Burnside's lemma).
        """
        if not self.generators:
            return float(self.n_features)
        total = sum(self.characters.values())
        return total / len(self.generators)

    def orbit_count(self) -> int:
        """Number of orbits under G (Burnside's lemma)."""
        return int(round(self.multiplicity_of_trivial()))

    def summary(self) -> str:
        if not self.characters:
            self.build()
        lines = [
            f"Character Table — {self.group_description}",
            f"  Feature space dim: {self.n_features}",
            f"  Generators: {len(self.generators)}",
        ]
        for i, chi in self.characters.items():
            lines.append(f"  χ(g{i}) = {chi} fixed points")
        lines.append(f"  ⟨χ, χ⟩ = {self.inner_product(self.compute_character, self.compute_character):.2f} irreducible components (approx)")
        lines.append(f"  Orbits (Burnside): {self.orbit_count()}")
        return "\n".join(lines)


@dataclass
class OrbitDecomposition:
    """Partition of feature space into orbits under group action.

    Two features are in the same orbit if some sequence of generators
    maps one to the other. Features in the same orbit are "equivalent
    up to transformation" — they are variations of the same invariant.
    """
    orbits: List[Set[int]] = field(default_factory=list)
    orbit_of: Dict[int, int] = field(default_factory=dict)  # feature_idx → orbit_id
    orbit_labels: Dict[int, str] = field(default_factory=dict)  # orbit_id → label

    def features_in_orbit(self, orbit_id: int) -> Set[int]:
        return self.orbits[orbit_id] if orbit_id < len(self.orbits) else set()

    def orbit_id_for(self, feature_idx: int) -> Optional[int]:
        return self.orbit_of.get(feature_idx)

    def n_orbits(self) -> int:
        return len(self.orbits)

    def is_trivial(self) -> bool:
        """True if every orbit has size 1 (no non-trivial symmetries)."""
        return all(len(o) == 1 for o in self.orbits)

    def orbit_sizes(self) -> List[int]:
        return [len(o) for o in self.orbits]


@dataclass
class InvariantProfile:
    """The extracted invariant profile for a problem or problem type.

    Organizes features into three tiers:
      - core: always present, fully invariant (the "DNA")
      - structural: invariant under some but not all transformations
      - variable: not invariant, changes across instances
    """
    problem_id: str = ""
    problem_type: str = ""
    core_invariants: List[Tuple[str, ...]] = field(default_factory=list)
    structural_invariants: List[Tuple[str, ...]] = field(default_factory=list)
    variable_features: List[str] = field(default_factory=list)
    invariance_scores: Dict[Tuple[str, ...], float] = field(default_factory=dict)
    supporting_rules: List[Dict] = field(default_factory=list)
    transformation_group_desc: str = ""
    orbit_summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EssenceReport:
    """Full essence analysis report for a problem domain."""
    domain: str
    n_problems: int
    profiles: List[InvariantProfile] = field(default_factory=list)
    cross_problem_invariants: List[Tuple[str, ...]] = field(default_factory=list)
    domain_essence: List[Tuple[str, ...]] = field(default_factory=list)
    transformation_groups: List[str] = field(default_factory=list)


# ─── Group Construction ────────────────────────────────────────────────────────

def build_transformation_group(
    space: FeatureSpace,
    rules: List[TransformationRule],
) -> PermutationGroup:
    """Build a permutation group from semantic transformation rules.

    Each TransformationRule specifies a set of features that should be
    treated as equivalent. For a group of n equivalent features, we
    generate transpositions (i, i+1) for i = 1..n-1. These transpositions
    generate the full symmetric group S_n on that subset.
    """
    group = PermutationGroup()
    for rule in rules:
        indices = []
        for feat in rule.feature_group:
            if feat in space:
                indices.append(space.feature_to_idx[feat])
        if len(indices) < 2:
            continue
        # Adjacent transpositions generate S_n on this subset
        for i in range(len(indices) - 1):
            group.add_transposition(indices[i], indices[i + 1])
    return group


def build_domain_transformation_rules() -> List[TransformationRule]:
    """Return the standard transformation rules for CTF problem domains.

    These rules capture known equivalences in forensic/security tools,
    encoding formats, and algorithm variants.
    """
    rules = []

    # ── Tool aliases & versions ──
    rules.append(TransformationRule(
        name="volatility_aliases",
        description="Volatility memory forensics tool aliases",
        feature_group=["volatility", "volatility3", "vol3", "vol2", "vol"],
        domain="memory_forensics",
    ))
    rules.append(TransformationRule(
        name="disk_mount_tools",
        description="Disk image mount tools are interchangeable",
        feature_group=["ewfmount", "mount", "losetup", "imagemount", " Arsenal_mount"],
        domain="disk_forensics",
    ))
    rules.append(TransformationRule(
        name="registry_tools",
        description="Windows registry analysis tools",
        feature_group=["regripper", "registry_explorer", "regedit", "recmd", "reg"],
        domain="windows_forensics",
    ))
    rules.append(TransformationRule(
        name="sqlite_tools",
        description="SQLite database forensics tools",
        feature_group=["sqlite3", "sqlitebrowser", "db_browser", "sqlite"],
        domain="mobile_forensics",
    ))
    rules.append(TransformationRule(
        name="network_capture_tools",
        description="Network traffic analysis tools",
        feature_group=["wireshark", "tshark", "tcpdump", "networkminer"],
        domain="network_forensics",
    ))
    rules.append(TransformationRule(
        name="python_versions",
        description="Python version aliases",
        feature_group=["python", "python3", "python310", "python311", "python312"],
        domain="general",
    ))

    # ── Encoding variants ──
    rules.append(TransformationRule(
        name="text_encodings",
        description="Text encoding formats are representation variants",
        feature_group=["base64", "base32", "hex", "ascii", "utf8", "rot13", "url_encode"],
        domain="crypto",
    ))
    rules.append(TransformationRule(
        name="archive_formats",
        description="Archive/compression formats",
        feature_group=["zip", "tar", "gz", "7z", "rar", "bz2", "xz"],
        domain="general",
    ))

    # ── Crypto algorithm variants ──
    rules.append(TransformationRule(
        name="rsa_variants",
        description="RSA with different key sizes share the same mathematical essence",
        feature_group=["rsa", "rsa_1024", "rsa_2048", "rsa_4096"],
        domain="crypto",
    ))
    rules.append(TransformationRule(
        name="aes_variants",
        description="AES with different modes share the block-cipher essence",
        feature_group=["aes", "aes_ecb", "aes_cbc", "aes_ctr", "aes_gcm", "aes_256"],
        domain="crypto",
    ))
    rules.append(TransformationRule(
        name="hash_variants",
        description="Cryptographic hash function variants",
        feature_group=["md5", "sha1", "sha256", "sha512", "blake2"],
        domain="crypto",
    ))
    rules.append(TransformationRule(
        name="ecc_variants",
        description="Elliptic curve variants",
        feature_group=["ecc", "ecdsa", "ecdh", "ed25519", "secp256k1"],
        domain="crypto",
    ))

    # ── Stego techniques ──
    rules.append(TransformationRule(
        name="stego_image",
        description="Image steganography techniques",
        feature_group=["lsb", "dct", "dwt", "pixel", "exif", "metadata_stego"],
        domain="stego",
    ))
    rules.append(TransformationRule(
        name="stego_audio",
        description="Audio steganography techniques",
        feature_group=["audio_lsb", "spectrum", "echo_hiding", "phase_coding"],
        domain="stego",
    ))

    # ── Forensics evidence types ──
    rules.append(TransformationRule(
        name="memory_images",
        description="Memory dump image formats",
        feature_group=["raw", "vmem", "mem", "dmp", "elf_core", "lime"],
        domain="memory_forensics",
    ))
    rules.append(TransformationRule(
        name="disk_images",
        description="Disk image formats",
        feature_group=["e01", "dd", "raw_disk", "vmdk", "vhd", "qcow2", "aff4"],
        domain="disk_forensics",
    ))

    # ── Binary analysis ──
    rules.append(TransformationRule(
        name="disassemblers",
        description="Disassembler/decompiler tools are functionally equivalent",
        feature_group=["ida", "ghidra", "radare2", "binary_ninja", "objdump", "rizin"],
        domain="binary_analysis",
    ))
    rules.append(TransformationRule(
        name="binary_formats",
        description="Binary executable formats",
        feature_group=["elf", "pe", "macho", "exe", "dll", "so"],
        domain="binary_analysis",
    ))

    return rules


def compute_orbit_decomposition(
    space: FeatureSpace,
    group: PermutationGroup,
) -> OrbitDecomposition:
    """Partition all features into orbits under the permutation group.

    Uses union-find on the generator set to compute connected components
    in the undirected graph where edges = transpositions.
    """
    n = len(space)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for gen in group.generators:
        for i, j in gen.mapping.items():
            if i < n and j < n:
                union(i, j)

    orbit_map: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        orbit_map[find(i)].append(i)

    decomp = OrbitDecomposition()
    for root, members in sorted(orbit_map.items()):
        orbit_id = len(decomp.orbits)
        decomp.orbits.append(set(members))
        for m in members:
            decomp.orbit_of[m] = orbit_id
        # Label the orbit by its most frequent representative
        if members:
            label = space.features[members[0]]
            decomp.orbit_labels[orbit_id] = label

    return decomp


# ─── Invariant Extraction ──────────────────────────────────────────────────────

def _itemset_to_frozenset_str(itemset: Tuple[str, ...]) -> FrozenSet[str]:
    return frozenset(itemset)


class InvariantExtractor:
    """Extracts problem invariants by fusing Apriori and group theory.

    Usage:
        extractor = InvariantExtractor(problem_signatures, space, group)
        essence = extractor.extract_essence(min_support=0.3, min_invariance=0.5)
    """

    def __init__(
        self,
        problems: List[ProblemSignature],
        space: Optional[FeatureSpace] = None,
        group: Optional[PermutationGroup] = None,
        rules: Optional[List[TransformationRule]] = None,
    ):
        self.problems = problems
        self._rules = rules  # stored for reporting
        self.space = space or self._build_feature_space(problems)
        self.group = group or build_transformation_group(
            self.space, self._rules or build_domain_transformation_rules()
        )
        self.orbit_decomp = compute_orbit_decomposition(self.space, self.group)
        self._transactions: Optional[List[Set[str]]] = None

    @staticmethod
    def _build_feature_space(problems: List[ProblemSignature]) -> FeatureSpace:
        space = FeatureSpace()
        for p in problems:
            for feat in sorted(p.features):
                domain = p.domain
                space.add_feature(feat, domain)
        return space

    def _get_transactions(self) -> List[Set[str]]:
        if self._transactions is None:
            self._transactions = [p.features for p in self.problems]
        return self._transactions

    def extract_essence(
        self,
        min_support: float = 0.3,
        min_invariance: float = 0.5,
        max_k: int = 5,
    ) -> EssenceReport:
        """Run the full fusion pipeline and return an EssenceReport.

        Args:
            min_support: Minimum support for Apriori frequent itemsets.
            min_invariance: Minimum invariance degree for "core" invariants.
            max_k: Maximum itemset size to explore.

        Returns:
            EssenceReport with per-problem and cross-problem invariants.
        """
        from tools.analytics.apriori import generate_frequent_itemsets

        txns = self._get_transactions()

        # Step 1: Apriori → candidate frequent itemsets
        frequent = generate_frequent_itemsets(txns, min_support=min_support, max_k=max_k)

        # Flatten all frequent itemsets
        all_freq: Dict[FrozenSet[str], float] = {}
        for k_itemsets in frequent.values():
            for itemset, support in k_itemsets.items():
                fs = frozenset(itemset)
                if fs not in all_freq or support > all_freq[fs]:
                    all_freq[fs] = support

        # Step 2: Score each itemset by both frequency AND invariance
        scored = self._score_itemsets(all_freq)

        # Step 3: Classify into tiers
        core = []
        structural = []
        variable = []
        for fs, (support, inv_deg, _) in scored.items():
            itemset = tuple(sorted(fs))
            if inv_deg >= 0.9 and support >= min_support * 2:
                core.append(itemset)
            elif inv_deg >= min_invariance:
                structural.append(itemset)

        # Variable features: singleton features with low invariance
        for feat in self.space.features:
            fs = frozenset({feat})
            if fs not in scored or scored[fs][1] < min_invariance:
                variable.append(feat)

        # Step 4: Compute cross-problem invariants (itemsets invariant across >= 80% problems)
        cross = self._cross_problem_invariants(all_freq, min_support)

        # Step 5: Build per-problem profiles
        profiles = []
        for p in self.problems:
            profile = self._profile_for_problem(p, all_freq, scored)
            profiles.append(profile)

        # Step 6: Domain essence = intersection of all per-problem core invariants
        if profiles:
            domain_essence = list(set.intersection(*[
                {tuple(sorted(fs)) for fs in self._problem_core(p, all_freq, scored)}
                for p in self.problems
            ])) if len(self.problems) > 1 else profiles[0].core_invariants
        else:
            domain_essence = []

        # Determine primary domain
        domain = self.problems[0].domain if self.problems else "unknown"
        domains = set(p.domain for p in self.problems if p.domain)
        if len(domains) == 1:
            domain = domains.pop()

        return EssenceReport(
            domain=domain,
            n_problems=len(self.problems),
            profiles=profiles,
            cross_problem_invariants=cross,
            domain_essence=domain_essence,
            transformation_groups=[f"{g.name}: {g.description}"
                                   for g in (self._rules or [])],
        )

    def _score_itemsets(
        self, all_freq: Dict[FrozenSet[str], float]
    ) -> Dict[FrozenSet[str], Tuple[float, float, float]]:
        """Score each itemset: (support, invariance_degree, combined_score).

        combined_score = support * invariance_degree
        This rewards itemsets that are BOTH frequent and invariant.
        """
        scored = {}
        for fs, support in all_freq.items():
            orbit_size = self.group.orbit_size(fs, self.space)
            # Normalize: larger space -> more potential variation
            max_orbit = max(1, len(self.space.features))
            inv_deg = 1.0 - (orbit_size - 1) / max_orbit
            inv_deg = max(0.0, min(1.0, inv_deg))

            # Also consider partial invariance (generator-fixing ratio)
            partial = self.group.partial_invariance(fs, self.space)
            combined_inv = 0.7 * inv_deg + 0.3 * partial

            combined_score = support * combined_inv
            scored[fs] = (support, combined_inv, combined_score)
        return scored

    def _problem_core(
        self, p: ProblemSignature,
        all_freq: Dict[FrozenSet[str], float],
        scored: Dict[FrozenSet[str], Tuple[float, float, float]],
    ) -> Set[FrozenSet[str]]:
        """Get core invariant itemsets for a specific problem."""
        core = set()
        p_fs = frozenset(p.features)
        for fs in all_freq:
            if fs.issubset(p_fs) and fs in scored:
                _, inv_deg, _ = scored[fs]
                if inv_deg >= 0.9:
                    core.add(fs)
        return core

    def _profile_for_problem(
        self, p: ProblemSignature,
        all_freq: Dict[FrozenSet[str], float],
        scored: Dict[FrozenSet[str], Tuple[float, float, float]],
    ) -> InvariantProfile:
        """Build an InvariantProfile for a single problem."""
        p_fs = frozenset(p.features)

        core = []
        structural = []
        scores = {}

        for fs in all_freq:
            if not fs.issubset(p_fs):
                continue
            if fs not in scored:
                continue
            support, inv_deg, combined = scored[fs]
            itemset = tuple(sorted(fs))
            scores[itemset] = inv_deg
            if inv_deg >= 0.9:
                core.append(itemset)
            elif inv_deg >= 0.5:
                structural.append(itemset)

        # Sort by combined score
        core.sort(key=lambda x: scores.get(x, 0), reverse=True)
        structural.sort(key=lambda x: scores.get(x, 0), reverse=True)

        # Variable features = features not in any core/structural invariant
        all_invariant_features = set()
        for itemset in core + structural:
            all_invariant_features.update(itemset)
        variable = sorted(p.features - all_invariant_features)

        return InvariantProfile(
            problem_id=p.problem_id,
            problem_type=p.domain or "unknown",
            core_invariants=core,
            structural_invariants=structural,
            variable_features=variable,
            invariance_scores=scores,
            transformation_group_desc=f"{self.group.n_generators()} generators, "
                                     f"{self.orbit_decomp.n_orbits()} orbits",
            orbit_summary={
                "n_orbits": self.orbit_decomp.n_orbits(),
                "nontrivial_orbits": sum(
                    1 for o in self.orbit_decomp.orbits if len(o) > 1
                ),
                "orbit_sizes": self.orbit_decomp.orbit_sizes(),
            },
        )

    def _cross_problem_invariants(
        self,
        all_freq: Dict[FrozenSet[str], float],
        min_support: float,
    ) -> List[Tuple[str, ...]]:
        """Find itemsets that are invariant across all problems of this type."""
        if not self.problems:
            return []

        problem_sets = [frozenset(p.features) for p in self.problems]

        candidates = []
        for fs, support in all_freq.items():
            if support < min_support:
                continue
            # Check: is this itemset invariant under the group?
            if self.group.is_invariant(fs, self.space):
                # Check: does it appear in most problems?
                n_contains = sum(1 for ps in problem_sets if fs.issubset(ps))
                if n_contains >= len(problem_sets) * 0.8:
                    candidates.append((support, tuple(sorted(fs))))

        candidates.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        return [itemset for _, itemset in candidates]


# ─── Differential Analysis ─────────────────────────────────────────────────────

def compare_problem_essences(
    profile_a: InvariantProfile,
    profile_b: InvariantProfile,
) -> Dict:
    """Compare two problems' invariant profiles to highlight what differs.

    Returns a diff showing:
      - shared_core: invariants both problems share (the problem TYPE essence)
      - unique_to_a / unique_to_b: what makes each problem distinct
      - shared_structural: structural invariants in common
    """
    core_a = {tuple(sorted(c)) for c in profile_a.core_invariants}
    core_b = {tuple(sorted(c)) for c in profile_b.core_invariants}
    struct_a = {tuple(sorted(s)) for s in profile_a.structural_invariants}
    struct_b = {tuple(sorted(s)) for s in profile_b.structural_invariants}

    return {
        "shared_core": sorted(core_a & core_b, key=lambda x: (-len(x), x)),
        "unique_to_a_core": sorted(core_a - core_b, key=lambda x: (-len(x), x)),
        "unique_to_b_core": sorted(core_b - core_a, key=lambda x: (-len(x), x)),
        "shared_structural": sorted(struct_a & struct_b, key=lambda x: (-len(x), x)),
        "a_id": profile_a.problem_id,
        "b_id": profile_b.problem_id,
    }


def find_analogous_problems(
    profiles: List[InvariantProfile],
    min_shared_core: int = 2,
) -> List[Tuple[str, str, int, List[Tuple[str, ...]]]]:
    """Find pairs of problems that share core invariants (analogous structure).

    Returns list of (problem_id_a, problem_id_b, n_shared, shared_core_itemsets).
    """
    results = []
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            diff = compare_problem_essences(profiles[i], profiles[j])
            if len(diff["shared_core"]) >= min_shared_core:
                results.append((
                    profiles[i].problem_id,
                    profiles[j].problem_id,
                    len(diff["shared_core"]),
                    diff["shared_core"],
                ))
    results.sort(key=lambda x: -x[2])
    return results


# ─── Isomorphism Recognition ───────────────────────────────────────────────────

@dataclass
class InvariantStructureGraph:
    """A graph capturing the invariant structure of a problem.

    Nodes = invariant features (flattened from core + structural itemsets).
    Edges = co-occurrence within same itemset (features that appear together
           in an invariant itemset are structurally linked).

    This graph is domain-agnostic: two problems from different domains can
    have isomorphic graphs even though their feature labels differ.
    """
    problem_id: str = ""
    domain: str = ""
    nodes: Set[str] = field(default_factory=set)
    edges: Set[Tuple[str, str]] = field(default_factory=set)
    node_weights: Dict[str, float] = field(default_factory=dict)  # invariance degree
    signature: Dict[str, Any] = field(default_factory=dict)

    def n_nodes(self) -> int: return len(self.nodes)
    def n_edges(self) -> int: return len(self.edges)

    def adjacency(self, node: str) -> Set[str]:
        neighbors = set()
        for a, b in self.edges:
            if a == node:
                neighbors.add(b)
            elif b == node:
                neighbors.add(a)
        return neighbors

    def degree(self, node: str) -> int:
        return len(self.adjacency(node))

    def degree_sequence(self) -> List[int]:
        return sorted([self.degree(n) for n in self.nodes], reverse=True)

    def clustering_coefficient(self, node: str) -> float:
        neighbors = self.adjacency(node)
        k = len(neighbors)
        if k < 2:
            return 0.0
        possible_edges = k * (k - 1) // 2
        actual_edges = sum(1 for a, b in combinations(neighbors, 2)
                          if (a, b) in self.edges or (b, a) in self.edges)
        return actual_edges / possible_edges

    def avg_clustering(self) -> float:
        coeffs = [self.clustering_coefficient(n) for n in self.nodes if self.degree(n) >= 2]
        return sum(coeffs) / len(coeffs) if coeffs else 0.0


def build_invariant_graph(profile: InvariantProfile) -> InvariantStructureGraph:
    """Build a structure graph from an invariant profile.

    Nodes = all features appearing in core or structural invariants.
    Edges = features that co-occur within the same invariant itemset.
    """
    graph = InvariantStructureGraph(
        problem_id=profile.problem_id,
        domain=profile.problem_type,
    )

    all_itemsets = profile.core_invariants + profile.structural_invariants
    for itemset in all_itemsets:
        for item in itemset:
            graph.nodes.add(item)
            graph.node_weights[item] = max(
                graph.node_weights.get(item, 0),
                profile.invariance_scores.get(itemset, 0),
            )
        for a, b in combinations(sorted(itemset), 2):
            edge = (a, b) if a < b else (b, a)
            graph.edges.add(edge)

    graph.signature = compute_graph_signature(graph)
    return graph


def compute_graph_signature(graph: InvariantStructureGraph) -> Dict[str, Any]:
    """Compute a structural fingerprint of an invariant graph.

    The signature is a vector of graph-theoretic invariants that are
    themselves invariant under node relabeling — making them suitable
    for cross-domain isomorphism detection.
    """
    deg_seq = graph.degree_sequence()
    return {
        "n_nodes": graph.n_nodes(),
        "n_edges": graph.n_edges(),
        "density": (2 * graph.n_edges() / (graph.n_nodes() * (graph.n_nodes() - 1)))
                   if graph.n_nodes() > 1 else 0.0,
        "max_degree": max(deg_seq) if deg_seq else 0,
        "min_degree": min(deg_seq) if deg_seq else 0,
        "avg_degree": sum(deg_seq) / len(deg_seq) if deg_seq else 0,
        "degree_variance": (sum((d - (sum(deg_seq)/len(deg_seq)))**2 for d in deg_seq) / len(deg_seq))
                           if deg_seq else 0.0,
        "avg_clustering": graph.avg_clustering(),
        "n_components": _count_components(graph),
        "n_isolated": sum(1 for n in graph.nodes if graph.degree(n) == 0),
    }


def _count_components(graph: InvariantStructureGraph) -> int:
    """Count connected components via DFS."""
    visited = set()
    components = 0
    for node in graph.nodes:
        if node not in visited:
            components += 1
            stack = [node]
            while stack:
                v = stack.pop()
                if v not in visited:
                    visited.add(v)
                    stack.extend(graph.adjacency(v) - visited)
    return components


@dataclass
class IsomorphismMapping:
    """A detected isomorphism between two problems from different domains."""
    source_id: str
    source_domain: str
    target_id: str
    target_domain: str
    isomorphism_type: str  # "exact", "strong", "partial", "analogical"
    score: float            # 0.0 - 1.0
    signature_similarity: float
    graph_overlap_ratio: float
    shared_core_count: int
    feature_mapping: Dict[str, str] = field(default_factory=dict)
    structural_differences: List[str] = field(default_factory=list)
    interpretation: str = ""


def detect_isomorphisms(
    profiles: List[InvariantProfile],
    min_score: float = 0.4,
    cross_domain_only: bool = True,
) -> List[IsomorphismMapping]:
    """Detect isomorphic problem pairs across (optionally) different domains.

    For each pair of profiles, builds invariant structure graphs and computes
    isomorphism score based on graph signature similarity and core overlap.

    Args:
        profiles: List of invariant profiles from potentially different domains.
        min_score: Minimum isomorphism score to report.
        cross_domain_only: If True, only report pairs from DIFFERENT domains.

    Returns:
        List of IsomorphismMapping sorted by score descending.
    """
    graphs = {p.problem_id: build_invariant_graph(p) for p in profiles}
    results = []

    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            pi, pj = profiles[i], profiles[j]
            if cross_domain_only and pi.problem_type == pj.problem_type:
                continue

            gi, gj = graphs[pi.problem_id], graphs[pj.problem_id]
            mapping = _compute_isomorphism(pi, pj, gi, gj)

            if mapping.score >= min_score:
                results.append(mapping)

    results.sort(key=lambda m: m.score, reverse=True)
    return results


def _compute_isomorphism(
    profile_a: InvariantProfile,
    profile_b: InvariantProfile,
    graph_a: InvariantStructureGraph,
    graph_b: InvariantStructureGraph,
) -> IsomorphismMapping:
    """Compute isomorphism details between two profiles and their graphs."""

    # 1. Graph signature similarity (cosine)
    sig_a = graph_a.signature
    sig_b = graph_b.signature
    sig_keys = ["n_nodes", "n_edges", "density", "avg_degree", "avg_clustering",
                "n_components", "n_isolated"]
    vec_a = [sig_a.get(k, 0) for k in sig_keys]
    vec_b = [sig_b.get(k, 0) for k in sig_keys]
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    sig_sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0

    # 2. Core invariant overlap (Jaccard on feature sets)
    features_a = set().union(*[{item for item in itemset}
                               for itemset in profile_a.core_invariants]) if profile_a.core_invariants else set()
    features_b = set().union(*[{item for item in itemset}
                               for itemset in profile_b.core_invariants]) if profile_b.core_invariants else set()
    all_features_a = set().union(*[{item for item in itemset}
                                    for itemset in profile_a.core_invariants + profile_a.structural_invariants]) if (profile_a.core_invariants or profile_a.structural_invariants) else set()
    all_features_b = set().union(*[{item for item in itemset}
                                    for itemset in profile_b.core_invariants + profile_b.structural_invariants]) if (profile_b.core_invariants or profile_b.structural_invariants) else set()

    union = len(all_features_a | all_features_b)
    intersection = len(all_features_a & all_features_b)
    overlap_ratio = intersection / union if union > 0 else 0.0

    # 3. Shared core count
    shared = compare_problem_essences(profile_a, profile_b)
    shared_core_count = len(shared["shared_core"])

    # 4. Feature mapping via orbit-based semantic similarity
    feature_mapping = _build_feature_mapping(graph_a, graph_b)

    # 5. Composite score: weighted combination
    score = 0.35 * sig_sim + 0.25 * overlap_ratio + 0.25 * min(1.0, shared_core_count / 5) + 0.15 * min(1.0, len(feature_mapping) / 3)

    # 6. Classify isomorphism type
    if sig_sim >= 0.9 and overlap_ratio >= 0.6 and shared_core_count >= 3:
        iso_type = "exact"
        interp = f"精确同构: {profile_a.problem_type} 和 {profile_b.problem_type} 共享完全相同的结构骨架。跨域知识可直接迁移。"
    elif sig_sim >= 0.7 and (overlap_ratio >= 0.4 or shared_core_count >= 2):
        iso_type = "strong"
        interp = f"强同构: 核心结构高度一致，仅部分实现细节不同。跨域知识迁移置信度高。"
    elif sig_sim >= 0.5 or shared_core_count >= 2:
        iso_type = "partial"
        interp = f"部分同构: 存在共享子结构。可迁移特定子问题的解法，但不能全盘照搬。"
    else:
        iso_type = "analogical"
        interp = f"类比同构: 结构相似度较低但存在可类比的特征映射。跨域启发式迁移。"

    # 7. Structural differences
    diffs = []
    if abs(sig_a["n_nodes"] - sig_b["n_nodes"]) > 3:
        diffs.append(f"节点数差异: {sig_a['n_nodes']} vs {sig_b['n_nodes']}")
    if abs(sig_a["avg_clustering"] - sig_b["avg_clustering"]) > 0.2:
        diffs.append(f"聚类系数差异显著: {sig_a['avg_clustering']:.2f} vs {sig_b['avg_clustering']:.2f}")
    if graph_a.n_nodes() > 0 and graph_b.n_nodes() > 0:
        if abs(sig_a["density"] - sig_b["density"]) > 0.3:
            diffs.append(f"图密度差异: {sig_a['density']:.2f} vs {sig_b['density']:.2f}")

    return IsomorphismMapping(
        source_id=profile_a.problem_id,
        source_domain=profile_a.problem_type,
        target_id=profile_b.problem_id,
        target_domain=profile_b.problem_type,
        isomorphism_type=iso_type,
        score=round(score, 4),
        signature_similarity=round(sig_sim, 4),
        graph_overlap_ratio=round(overlap_ratio, 4),
        shared_core_count=shared_core_count,
        feature_mapping=feature_mapping,
        structural_differences=diffs,
        interpretation=interp,
    )


def _build_feature_mapping(
    graph_a: InvariantStructureGraph,
    graph_b: InvariantStructureGraph,
) -> Dict[str, str]:
    """Build a feature mapping between two graphs based on structural role.

    Two features map to each other if they have similar degree, similar
    clustering coefficient, and similar neighborhood size.
    """
    mapping = {}
    used_b = set()

    for node_a in graph_a.nodes:
        deg_a = graph_a.degree(node_a)
        clust_a = graph_a.clustering_coefficient(node_a)
        best_match = None
        best_score = 0.0

        for node_b in graph_b.nodes:
            if node_b in used_b:
                continue
            deg_b = graph_b.degree(node_b)
            clust_b = graph_b.clustering_coefficient(node_b)

            deg_score = 1.0 - abs(deg_a - deg_b) / max(1, deg_a + deg_b)
            clust_score = 1.0 - abs(clust_a - clust_b)
            match_score = 0.6 * deg_score + 0.4 * clust_score

            if match_score > best_score and match_score >= 0.6:
                best_score = match_score
                best_match = node_b

        if best_match and best_score >= 0.6:
            mapping[node_a] = best_match
            used_b.add(best_match)

    return mapping


# ─── Cross-Domain Knowledge Transfer ────────────────────────────────────────────

# Domain-specific tool and technique mapping tables
_CROSS_DOMAIN_TOOL_MAP = {
    # Crypto → Binary: mathematical decomposition
    ("crypto", "binary_analysis"): {
        "sage": "ida",
        "python": "python",
        "rsa": "rsa_pubkey_in_binary",
        "factorization": "decompilation",
        "openssl": "ghidra",
        "z3": "angr",
    },
    # Crypto → Stego: encoding/decoding
    ("crypto", "stego"): {
        "python": "python",
        "base64": "base64_decode",
        "xor": "lsb_xor",
        "frequency_analysis": "histogram_analysis",
        "openssl": "steghide",
        "cyberchef": "cyberchef",
    },
    # Memory → Disk: evidence extraction
    ("memory_forensics", "disk_forensics"): {
        "vol3": "tsk_recover",
        "volatility": "autopsy",
        "strings": "strings",
        "sqlite3": "sqlite3",
        "registry": "registry_explorer",
        "mft_parser": "mft_parser",
    },
    # Network → Binary: traffic → code analysis
    ("network_forensics", "binary_analysis"): {
        "wireshark": "ida",
        "tshark": "objdump",
        "pcap": "elf_parser",
        "dns_exfil": "data_encoding",
        "http_analysis": "api_tracing",
    },
    # Binary → Crypto: reverse → mathematical
    ("binary_analysis", "crypto"): {
        "ida": "sage",
        "ghidra": "python",
        "decompilation": "factorization",
        "angr": "z3",
        "obfuscation": "custom_encoding",
    },
}

_CROSS_DOMAIN_TECHNIQUE_MAP = {
    # Structural technique analogies
    ("crypto", "binary_analysis"): {
        "modular_arithmetic": "register_operations",
        "prime_factorization": "control_flow_decomposition",
        "padding_oracle": "buffer_overflow_detection",
        "side_channel": "timing_analysis",
        "brute_force": "fuzzing",
        "meet_in_the_middle": "bidirectional_analysis",
    },
    ("memory_forensics", "network_forensics"): {
        "process_scanning": "packet_filtering",
        "dll_injection_detection": "payload_analysis",
        "hive_parsing": "protocol_parsing",
        "timeline_reconstruction": "session_reconstruction",
    },
    ("binary_analysis", "crypto"): {
        "control_flow_analysis": "algorithm_identification",
        "symbolic_execution": "algebraic_attack",
        "disassembly": "cipher_text_analysis",
        "patching": "key_recovery",
    },
}


@dataclass
class TransferRecipe:
    """A knowledge transfer recipe from source domain to target domain."""
    isomorphism: IsomorphismMapping
    tool_transfers: List[Dict] = field(default_factory=list)
    technique_transfers: List[Dict] = field(default_factory=list)
    mapped_features: List[Tuple[str, str]] = field(default_factory=list)
    transfer_steps: List[str] = field(default_factory=list)
    confidence: str = ""  # "high", "medium", "low"
    caveats: List[str] = field(default_factory=list)


def generate_transfer_recipe(
    isomorphism: IsomorphismMapping,
    source_profile: InvariantProfile,
    target_profile: InvariantProfile,
    source_features: Optional[Set[str]] = None,
) -> TransferRecipe:
    """Generate a cross-domain knowledge transfer recipe.

    Given a detected isomorphism between two problems from different domains,
    produces actionable guidance for applying domain A's solution approach
    to domain B's problem.

    Args:
        isomorphism: The detected isomorphism mapping.
        source_profile: The source problem's invariant profile.
        target_profile: The target problem's invariant profile.
        source_features: Optional specific features to focus transfer on.

    Returns:
        TransferRecipe with mapped tools, techniques, and step-by-step guidance.
    """
    recipe = TransferRecipe(isomorphism=isomorphism)
    src_dom = isomorphism.source_domain
    tgt_dom = isomorphism.target_domain

    # 1. Tool transfer
    tool_map = _get_tool_mapping(src_dom, tgt_dom)
    src_tools = {item for itemset in source_profile.core_invariants + source_profile.structural_invariants
                 for item in itemset}
    tgt_tools = {item for itemset in target_profile.core_invariants + target_profile.structural_invariants
                 for item in itemset}

    for src_tool in src_tools:
        if src_tool in tool_map:
            tgt_tool = tool_map[src_tool]
            recipe.tool_transfers.append({
                "source_tool": src_tool,
                "target_tool": tgt_tool,
                "rationale": f"{src_dom} 中的 `{src_tool}` 在 {tgt_dom} 中对应 `{tgt_tool}`",
                "confidence": "high" if tgt_tool in tgt_tools else "medium",
            })

    # 2. Technique transfer
    tech_map = _get_technique_mapping(src_dom, tgt_dom)
    all_src_features = set().union(*[{item for item in itemset}
                                      for itemset in source_profile.core_invariants + source_profile.structural_invariants]) if (source_profile.core_invariants or source_profile.structural_invariants) else set()
    for src_tech, tgt_tech in tech_map.items():
        if src_tech in all_src_features or any(src_tech in " ".join(itemset).lower()
                                                for itemset in source_profile.core_invariants):
            recipe.technique_transfers.append({
                "source_technique": src_tech,
                "target_technique": tgt_tech,
                "rationale": f"结构同构: `{src_tech}` ↔ `{tgt_tech}`",
            })

    # 3. Feature mapping from isomorphism
    recipe.mapped_features = [(k, v) for k, v in isomorphism.feature_mapping.items()]

    # 4. Generate transfer steps
    recipe.transfer_steps = _generate_transfer_steps(isomorphism, recipe)

    # 5. Confidence and caveats
    if isomorphism.isomorphism_type == "exact":
        recipe.confidence = "high"
    elif isomorphism.isomorphism_type == "strong":
        recipe.confidence = "medium"
    else:
        recipe.confidence = "low"
        recipe.caveats.append("同构度较低，迁移方案仅供启发式参考，不可直接套用。")

    if isomorphism.structural_differences:
        for diff in isomorphism.structural_differences:
            recipe.caveats.append(f"结构差异: {diff}")

    if len(recipe.mapped_features) < 3:
        recipe.caveats.append("可映射特征较少，跨域迁移粒度粗。")

    return recipe


# ─── Category Theory Integration ───────────────────────────────────────────────
# The hardcoded _CROSS_DOMAIN_TOOL_MAP and _CROSS_DOMAIN_TECHNIQUE_MAP are
# REPLACED by functor-based derivation. The maps below are kept as the
# initial registration data for DomainFunctor; new domain pairs are derived
# via functor composition rather than manual table extension.

_DEFAULT_FUNCTOR: "Optional[DomainFunctor]" = None


def get_default_domain_functor() -> "DomainFunctor":
    """Get or lazily build the default DomainFunctor with registered mappings."""
    global _DEFAULT_FUNCTOR
    if _DEFAULT_FUNCTOR is None:
        from tools.analytics.category import build_default_domain_functor
        _DEFAULT_FUNCTOR = build_default_domain_functor()
    return _DEFAULT_FUNCTOR


def build_transfer_natural_transformation(
    isomorphism: IsomorphismMapping,
    source_profile: Optional[InvariantProfile] = None,
    target_profile: Optional[InvariantProfile] = None,
) -> "TransferTransformation":
    """Build a NaturalTransformation η: F_src ⇒ F_tgt from an IsomorphismMapping.

    This formalizes cross-domain knowledge transfer as a natural
    transformation between domain functors. Each component η_D is a
    feature-space morphism encoding tool/technique translations.

    Args:
        isomorphism: Detected isomorphism between two domain problems.
        source_profile: Optional source invariant profile.
        target_profile: Optional target invariant profile.

    Returns:
        TransferTransformation with verified naturality conditions.
    """
    from tools.analytics.category import (
        TransferTransformation, build_default_domain_functor,
    )
    F = build_default_domain_functor()
    nt = TransferTransformation(
        source_functor=F,
        target_functor=F,
        source_domain=isomorphism.source_domain,
        target_domain=isomorphism.target_domain,
    )
    nt.build_from_isomorphism(isomorphism, source_profile, target_profile)
    return nt


def derive_tool_mapping_functorial(
    src_domain: str, tgt_domain: str
) -> Dict[str, str]:
    """Derive tool mapping via functor composition (replaces _get_tool_mapping).

    Uses DomainFunctor.derive_cross_domain_tools() which composes functor
    images along DomainCategory morphisms. Falls back to direct lookup
    (the registered maps) if no composition path is found.
    """
    F = get_default_domain_functor()
    result = F.derive_cross_domain_tools(src_domain, tgt_domain)
    if result:
        return result
    # Fallback: direct registered map
    return _get_tool_mapping(src_domain, tgt_domain)


def derive_technique_mapping_functorial(
    src_domain: str, tgt_domain: str
) -> Dict[str, str]:
    """Derive technique mapping via functor composition."""
    F = get_default_domain_functor()
    result = F.derive_cross_domain_techniques(src_domain, tgt_domain)
    if result:
        return result
    return _get_technique_mapping(src_domain, tgt_domain)


def generate_transfer_recipe_functorial(
    isomorphism: IsomorphismMapping,
    source_profile: Optional[InvariantProfile] = None,
    target_profile: Optional[InvariantProfile] = None,
    source_features: Optional[Set[str]] = None,
) -> TransferRecipe:
    """Generate transfer recipe using functorial (category-theoretic) approach.

    Unlike generate_transfer_recipe which uses hardcoded maps, this version
    builds a TransferTransformation (natural transformation between domain
    functors) and derives tool/technique mappings from the naturality condition.

    Args:
        isomorphism: The detected isomorphism mapping.
        source_profile: Optional source invariant profile.
        target_profile: Optional target invariant profile.
        source_features: Optional specific features to focus on.

    Returns:
        TransferRecipe with functor-derived mappings.
    """
    nt = build_transfer_natural_transformation(
        isomorphism, source_profile, target_profile,
    )
    naturality_ok, naturality_violations = nt.verify_naturality()

    recipe = TransferRecipe(isomorphism=isomorphism)

    # Derive tool and technique mappings from the natural transformation
    tool_map = nt.get_tool_mapping()
    tech_map = nt.get_technique_mapping()

    # If natural transformation didn't yield mapped features directly,
    # derive from the functor
    if not tool_map:
        tool_map = derive_tool_mapping_functorial(
            isomorphism.source_domain, isomorphism.target_domain,
        )
    if not tech_map:
        tech_map = derive_technique_mapping_functorial(
            isomorphism.source_domain, isomorphism.target_domain,
        )

    # Feature mapping from the isomorphism
    for src_feat, tgt_feat in isomorphism.feature_mapping.items():
        recipe.mapped_features.append((src_feat, tgt_feat))

    # Tool transfers from functorial derivation
    for src_tool, tgt_tool in tool_map.items():
        recipe.tool_transfers.append({
            "source_tool": src_tool,
            "target_tool": tgt_tool,
            "source": "functorial_derivation",
        })

    # Technique transfers
    for src_tech, tgt_tech in tech_map.items():
        recipe.technique_transfers.append({
            "source_technique": src_tech,
            "target_technique": tgt_tech,
            "source": "functorial_derivation",
        })

    # Confidence from isomorphism type and naturality
    if isomorphism.isomorphism_type == "exact" and naturality_ok:
        recipe.confidence = "high"
    elif isomorphism.isomorphism_type in ("exact", "strong"):
        recipe.confidence = "high" if naturality_ok else "medium"
    elif isomorphism.isomorphism_type == "partial":
        recipe.confidence = "medium" if naturality_ok else "low"
    else:
        recipe.confidence = "low"

    if isomorphism.structural_differences:
        for diff in isomorphism.structural_differences:
            recipe.caveats.append(f"结构差异: {diff}")

    if not naturality_ok:
        recipe.caveats.append(
            f"自然性条件不满足 ({len(naturality_violations)} 项违规)，"
            f"跨域映射可能不可靠。"
        )

    if len(recipe.mapped_features) < 3:
        recipe.caveats.append("可映射特征较少，跨域迁移粒度粗。")

    recipe.transfer_steps = _generate_transfer_steps(isomorphism, recipe)
    return recipe


def _get_tool_mapping(src_domain: str, tgt_domain: str) -> Dict[str, str]:
    """Get tool mapping for a domain pair (symmetric lookup)."""
    key = (src_domain, tgt_domain)
    if key in _CROSS_DOMAIN_TOOL_MAP:
        return _CROSS_DOMAIN_TOOL_MAP[key]
    rev_key = (tgt_domain, src_domain)
    if rev_key in _CROSS_DOMAIN_TOOL_MAP:
        # Reverse mapping
        return {v: k for k, v in _CROSS_DOMAIN_TOOL_MAP[rev_key].items()}
    return {}


def _get_technique_mapping(src_domain: str, tgt_domain: str) -> Dict[str, str]:
    """Get technique mapping for a domain pair (symmetric lookup)."""
    key = (src_domain, tgt_domain)
    if key in _CROSS_DOMAIN_TECHNIQUE_MAP:
        return _CROSS_DOMAIN_TECHNIQUE_MAP[key]
    rev_key = (tgt_domain, src_domain)
    if rev_key in _CROSS_DOMAIN_TECHNIQUE_MAP:
        return {v: k for k, v in _CROSS_DOMAIN_TECHNIQUE_MAP[rev_key].items()}
    return {}


def _generate_transfer_steps(
    isomorphism: IsomorphismMapping,
    recipe: TransferRecipe,
) -> List[str]:
    """Generate actionable transfer steps."""
    steps = []

    steps.append(
        f"确认同构类型: {isomorphism.isomorphism_type.upper()} "
        f"(得分 {isomorphism.score:.2f}) — "
        f"{isomorphism.source_domain} → {isomorphism.target_domain}"
    )

    if recipe.tool_transfers:
        top_tools = recipe.tool_transfers[:5]
        tool_str = "；".join(
            f"`{t['source_tool']}` → `{t['target_tool']}`"
            for t in top_tools
        )
        steps.append(f"工具迁移: {tool_str}")

    if recipe.technique_transfers:
        top_techs = recipe.technique_transfers[:5]
        tech_str = "；".join(
            f"`{t['source_technique']}` → `{t['target_technique']}`"
            for t in top_techs
        )
        steps.append(f"技术迁移: {tech_str}")

    if recipe.mapped_features:
        top_map = recipe.mapped_features[:5]
        map_str = "；".join(f"`{k}` ↔ `{v}`" for k, v in top_map)
        steps.append(f"特征映射: {map_str}")

    steps.append(
        f"执行策略: 将 {isomorphism.source_domain} 领域的解题流程映射到 "
        f"{isomorphism.target_domain} 领域，根据工具和技术对应表替换每一步骤的具体实现。"
    )

    if recipe.confidence == "low":
        steps.append("注意: 置信度较低，建议将迁移方案作为初步假设，在使用中根据实际结果调整。")

    return steps


# ─── Formatters ────────────────────────────────────────────────────────────────

def format_essence_report(report: EssenceReport) -> str:
    """Format a full EssenceReport as Chinese-language Markdown."""
    lines = [
        f"# 题目本质识别报告 — {report.domain}",
        f"",
        f"**分析范围**: {report.n_problems} 个题目",
        f"**变换群**: {', '.join(report.transformation_groups[:5]) or '(自动构建)'}",
        f"",
        "---",
        f"",
    ]

    # Domain essence
    if report.domain_essence:
        lines.append("## 域本质 (Domain Essence)")
        lines.append("")
        lines.append("> 该域所有题目共享的**不变核心** — 无论题目如何变换，这些特征始终存在。")
        lines.append("")
        for i, itemset in enumerate(report.domain_essence[:10], 1):
            items_str = " + ".join(f"`{item}`" for item in itemset)
            lines.append(f"**{i}.  {items_str}**")
        lines.append("")

    # Cross-problem invariants
    if report.cross_problem_invariants:
        lines.append("## 跨题不变量")
        lines.append("")
        lines.append("| # | 不变量组合 | 类型 |")
        lines.append("|---|---|---|")
        for i, itemset in enumerate(report.cross_problem_invariants[:15], 1):
            items_str = ", ".join(f"`{item}`" for item in itemset)
            inv_type = "核心" if len(itemset) <= 2 else "结构"
            lines.append(f"| {i} | {items_str} | {inv_type} |")
        lines.append("")

    # Per-problem profiles
    for profile in report.profiles[:10]:
        lines.append(f"### 题目: `{profile.problem_id}`")
        lines.append(f"")
        lines.append(f"**变换群**: {profile.transformation_group_desc}")
        lines.append(f"")

        if profile.core_invariants:
            lines.append(f"**核心不变量** (无论如何变换都不变):")
            lines.append(f"")
            for itemset in profile.core_invariants[:8]:
                items_str = " + ".join(f"`{item}`" for item in itemset)
                score = profile.invariance_scores.get(itemset, 0)
                lines.append(f"- {items_str}  *(不变度: {score:.0%})*")
            lines.append(f"")

        if profile.structural_invariants[:5]:
            lines.append(f"**结构不变量** (部分变换下保持):")
            lines.append(f"")
            for itemset in profile.structural_invariants[:5]:
                items_str = " + ".join(f"`{item}`" for item in itemset)
                score = profile.invariance_scores.get(itemset, 0)
                lines.append(f"- {items_str}  *(不变度: {score:.0%})*")
            lines.append(f"")

        if profile.variable_features[:8]:
            lines.append(f"**可变特征** (随实例变化):")
            lines.append(f"")
            lines.append(f"{' · '.join(f'`{v}`' for v in profile.variable_features[:8])}")
            lines.append(f"")

        orbit_sizes = profile.orbit_summary.get("orbit_sizes", [])
        nontriv = sum(1 for s in orbit_sizes if s > 1)
        lines.append(f"**轨道分析**: {profile.orbit_summary.get('n_orbits', '?')} 条轨道, "
                    f"{nontriv} 条非平凡轨道")
        lines.append(f"")
        lines.append("---")
        lines.append("")

    # Methodology guidance
    lines.append("## 方法论意义")
    lines.append("")
    lines.append("### 如何使用本质识别结果")
    lines.append("")
    lines.append("1. **核心不变量** = 该题型不可约简的知识骨架。训练时应优先掌握这些概念组合。")
    lines.append("2. **结构不变量** = 领域特定但存在变体的模式。掌握后可应对该题型的大部分变种。")
    lines.append("3. **可变特征** = 出题人可自由替换的部分。不应将解题策略绑定到具体工具上。")
    lines.append("4. **轨道** = 等价特征群。轨道内任一特征可替换为同轨道其他特征，不影响题目本质。")
    lines.append("")

    return "\n".join(lines)


def format_invariant_profile(profile: InvariantProfile) -> str:
    """Format a single InvariantProfile as Markdown."""
    lines = [
        f"## 题目本质: `{profile.problem_id}`",
        f"",
        f"**题目类型**: {profile.problem_type}",
        f"**变换群**: {profile.transformation_group_desc}",
        f"",
    ]

    if profile.core_invariants:
        lines.append("### 核心不变量 (无论如何变换都不变)")
        lines.append("")
        for i, itemset in enumerate(profile.core_invariants, 1):
            score = profile.invariance_scores.get(itemset, 0)
            items_str = ", ".join(itemset)
            lines.append(f"{i}. **{{{items_str}}}** — 不变度 {score:.0%}")
        lines.append("")

    if profile.structural_invariants:
        lines.append("### 结构不变量 (部分变换下保持)")
        lines.append("")
        for i, itemset in enumerate(profile.structural_invariants, 1):
            score = profile.invariance_scores.get(itemset, 0)
            items_str = ", ".join(itemset)
            lines.append(f"{i}. {{{items_str}}} — 不变度 {score:.0%}")
        lines.append("")

    if profile.variable_features:
        lines.append("### 可变特征")
        lines.append("")
        lines.append(", ".join(f"`{v}`" for v in profile.variable_features))
        lines.append("")

    return "\n".join(lines)


def format_essence_comparison(diff: Dict) -> str:
    """Format a comparison of two InvariantProfiles."""
    lines = [
        f"## 题目本质对比",
        f"",
        f"**题目 A**: `{diff['a_id']}`",
        f"**题目 B**: `{diff['b_id']}`",
        f"",
    ]

    if diff["shared_core"]:
        lines.append(f"### 共享核心 ({len(diff['shared_core'])} 个)")
        for c in diff["shared_core"][:10]:
            lines.append(f"- {{{', '.join(c)}}}")
        lines.append("")

    if diff["unique_to_a_core"]:
        lines.append(f"### 仅 A 有 ({len(diff['unique_to_a_core'])} 个)")
        for c in diff["unique_to_a_core"][:5]:
            lines.append(f"- {{{', '.join(c)}}}")
        lines.append("")

    if diff["unique_to_b_core"]:
        lines.append(f"### 仅 B 有 ({len(diff['unique_to_b_core'])} 个)")
        for c in diff["unique_to_b_core"][:5]:
            lines.append(f"- {{{', '.join(c)}}}")
        lines.append("")

    return "\n".join(lines)


def format_orbit_report(decomp: OrbitDecomposition, space: FeatureSpace) -> str:
    """Format orbit decomposition as Markdown."""
    lines = [
        "## 特征轨道分解",
        "",
        f"总轨道数: {decomp.n_orbits()}",
        f"非平凡轨道: {sum(1 for o in decomp.orbits if len(o) > 1)}",
        "",
        "| 轨道 | 大小 | 代表特征 | 等价特征群 |",
        "|---|---|---|---|",
    ]

    for oid, orbit in enumerate(decomp.orbits):
        if len(orbit) <= 1:
            continue
        features_in = sorted([space.features[i] for i in orbit])
        rep = features_in[0]
        others = ", ".join(f"`{f}`" for f in features_in[1:6])
        if len(features_in) > 6:
            others += f" ... (+{len(features_in) - 6})"
        lines.append(f"| {oid} | {len(orbit)} | `{rep}` | {others} |")

    if all(len(o) == 1 for o in decomp.orbits):
        lines.append("| — | — | (所有轨道均为平凡轨道) | — |")

    lines.append("")
    return "\n".join(lines)


# ─── Isomorphism & Transfer Formatters ────────────────────────────────────────

def format_isomorphism_report(
    isomorphisms: List[IsomorphismMapping],
    top_n: int = 20,
) -> str:
    """Format isomorphism detection results as Markdown."""
    if not isomorphisms:
        return "## 跨域同构分析\n\n未检测到同构题目对。尝试降低 min_score 阈值。\n"

    lines = [
        "## 跨域同构识别报告",
        "",
        f"共检测到 {len(isomorphisms)} 对跨域同构题目。",
        "",
        "| # | 源域 | 目标域 | 同构类型 | 得分 | 共享核心 | 图相似度 | 特征映射数 |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for i, iso in enumerate(isomorphisms[:top_n], 1):
        lines.append(
            f"| {i} | {iso.source_domain} | {iso.target_domain} | "
            f"**{iso.isomorphism_type}** | {iso.score:.3f} | "
            f"{iso.shared_core_count} | {iso.signature_similarity:.2f} | "
            f"{len(iso.feature_mapping)} |"
        )

    lines.append("")
    lines.append("### 同构详情")
    lines.append("")

    for i, iso in enumerate(isomorphisms[:10], 1):
        lines.append(f"#### {i}. [{iso.isomorphism_type.upper()}] "
                     f"{iso.source_domain} ↔ {iso.target_domain}")
        lines.append(f"- **得分**: {iso.score:.4f}")
        lines.append(f"- **解释**: {iso.interpretation}")
        lines.append(f"- **源题目**: `{iso.source_id}`")
        lines.append(f"- **目标题目**: `{iso.target_id}`")
        lines.append(f"- **共享核心不变量**: {iso.shared_core_count} 个")
        lines.append(f"- **图签名相似度**: {iso.signature_similarity:.2%}")
        lines.append(f"- **图重叠率**: {iso.graph_overlap_ratio:.2%}")

        if iso.feature_mapping:
            lines.append(f"- **特征映射**:")
            for src, tgt in list(iso.feature_mapping.items())[:8]:
                lines.append(f"  - `{src}` ↔ `{tgt}`")
            if len(iso.feature_mapping) > 8:
                lines.append(f"  - ... 共 {len(iso.feature_mapping)} 对映射")

        if iso.structural_differences:
            lines.append(f"- **结构差异**:")
            for diff in iso.structural_differences:
                lines.append(f"  - {diff}")

        lines.append("")

    lines.append("### 同构类型说明")
    lines.append("")
    lines.append("| 类型 | 条件 | 迁移置信度 |")
    lines.append("|---|---|---|")
    lines.append("| **exact** | 图签名相似度 ≥ 0.9, 重叠率 ≥ 0.6, 共享核心 ≥ 3 | 高 — 可直接迁移 |")
    lines.append("| **strong** | 签名相似度 ≥ 0.7, 重叠率 ≥ 0.4 或 共享核心 ≥ 2 | 中 — 迁移置信度高 |")
    lines.append("| **partial** | 签名相似度 ≥ 0.5 或 共享核心 ≥ 2 | 中低 — 可迁移子问题 |")
    lines.append("| **analogical** | 其他情况 | 低 — 启发式参考 |")
    lines.append("")

    return "\n".join(lines)


def format_transfer_recipe(recipe: TransferRecipe) -> str:
    """Format a cross-domain transfer recipe as Markdown."""
    iso = recipe.isomorphism
    lines = [
        f"# 跨域知识迁移方案",
        f"",
        f"**同构类型**: {iso.isomorphism_type.upper()} | **得分**: {iso.score:.4f} | **置信度**: {recipe.confidence}",
        f"",
        f"**源域**: {iso.source_domain} (`{iso.source_id}`)",
        f"**目标域**: {iso.target_domain} (`{iso.target_id}`)",
        f"",
        f"> {iso.interpretation}",
        f"",
        "---",
        f"",
    ]

    # Tool transfers
    if recipe.tool_transfers:
        lines.append("## 工具迁移")
        lines.append("")
        lines.append("| 源工具 | 目标工具 | 依据 | 置信度 |")
        lines.append("|---|---|---|---|")
        for t in recipe.tool_transfers[:15]:
            lines.append(
                f"| `{t['source_tool']}` | **`{t['target_tool']}`** | "
                f"{t['rationale']} | {t['confidence']} |"
            )
        lines.append("")

    # Technique transfers
    if recipe.technique_transfers:
        lines.append("## 技术迁移")
        lines.append("")
        lines.append("| 源技术 | 目标技术 | 依据 |")
        lines.append("|---|---|---|")
        for t in recipe.technique_transfers[:15]:
            lines.append(
                f"| `{t['source_technique']}` | **`{t['target_technique']}`** | "
                f"{t['rationale']} |"
            )
        lines.append("")

    # Feature mapping
    if recipe.mapped_features:
        lines.append("## 特征映射")
        lines.append("")
        lines.append("| 源特征 | 目标特征 |")
        lines.append("|---|---|")
        for src, tgt in recipe.mapped_features[:20]:
            lines.append(f"| `{src}` | `{tgt}` |")
        lines.append("")

    # Transfer steps
    if recipe.transfer_steps:
        lines.append("## 迁移执行步骤")
        lines.append("")
        for i, step in enumerate(recipe.transfer_steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    # Caveats
    if recipe.caveats:
        lines.append("## 注意事项")
        lines.append("")
        for caveat in recipe.caveats:
            lines.append(f"- ⚠ {caveat}")
        lines.append("")

    return "\n".join(lines)


def format_isomorphism_summary_table(
    isomorphisms: List[IsomorphismMapping],
) -> str:
    """Format a compact summary of all detected isomorphisms."""
    if not isomorphisms:
        return "未检测到跨域同构。"

    by_type = defaultdict(list)
    for iso in isomorphisms:
        by_type[iso.isomorphism_type].append(iso)

    lines = [
        "## 跨域同构摘要",
        "",
    ]

    for iso_type in ["exact", "strong", "partial", "analogical"]:
        items = by_type.get(iso_type, [])
        if items:
            lines.append(f"### {iso_type.upper()} ({len(items)} 对)")
            for iso in items[:5]:
                lines.append(
                    f"- {iso.source_domain} ↔ {iso.target_domain}: "
                    f"`{iso.source_id}` ↔ `{iso.target_id}` "
                    f"(得分 {iso.score:.3f}, 共享核心 {iso.shared_core_count})"
                )
            if len(items) > 5:
                lines.append(f"- ... 另有 {len(items) - 5} 对")
            lines.append("")

    return "\n".join(lines)


# ─── Group Action Knowledge Propagation ────────────────────────────────────────
#
# A permutation group G acting on knowledge atoms induces a propagation
# structure: g ∈ G maps atom a → a' when g applied to a's features yields
# the feature set of a'. The orbit G·a is all knowledge reachable from a.
# The stabilizer G_a is what transformations preserve a's meaning.
#
# Key concepts:
#   - Orbit G·a: all knowledge atoms reachable from a via group actions
#   - Stabilizer G_a: generators that leave a invariant (preserved properties)
#   - Cayley/Schreier graph: vertices = atoms, edges labeled by generators
#   - Propagation path: sequence g₁, g₂, ..., gₖ such that
#     gₖ∘...∘g₁ · a_source = a_target


@dataclass
class KnowledgeAtom:
    """A unit of knowledge that propagates through group actions.

    Each atom lives in a domain and carries features (tool names, techniques,
    mathematical structures). Group generators applied to these features
    determine how the atom transforms into others.
    """
    id: str
    domain: str
    content: str = ""
    features: FrozenSet[str] = field(default_factory=frozenset)
    atom_type: str = ""  # "tool", "technique", "insight", "solution", "problem"


@dataclass
class PropagationStep:
    """One atomic step in a knowledge propagation path."""
    from_atom: str
    to_atom: str
    generator_idx: int
    generator_name: str
    transformation_desc: str = ""


@dataclass
class PropagationPath:
    """A directed path showing how source knowledge propagates to target.

    Each step applies one group generator. Multi-step paths represent
    compositional knowledge transfer (间接迁移).
    """
    source_id: str
    target_id: str
    source_domain: str
    target_domain: str
    steps: List[PropagationStep] = field(default_factory=list)
    length: int = 0
    path_type: str = ""  # "direct", "composite", "isomorphic", "stabilized"
    confidence: float = 1.0


@dataclass
class PropagationNetwork:
    """The full knowledge propagation graph under group actions.

    Nodes are knowledge atoms. Directed edges are labeled by group generators:
    edge a → a' with label g means g·a = a' (applying generator g to a's
    features produces a feature set matching a').

    Also tracks domain-to-domain transition paths for cross-domain flow.
    """
    atoms: Dict[str, KnowledgeAtom] = field(default_factory=dict)
    transitions: Dict[str, List[Tuple[int, str]]] = field(default_factory=dict)
    generator_names: List[str] = field(default_factory=list)
    generator_descriptions: List[str] = field(default_factory=list)
    domain_transitions: Dict[Tuple[str, str], List[PropagationPath]] = field(
        default_factory=dict
    )


@dataclass
class GroupAction:
    """A group G acting on a set of knowledge atoms via feature permutations.

    The action φ: G × K → K maps (g, atom) to another atom by applying the
    permutation g to the atom's feature indices. If the resulting feature set
    matches another known atom, knowledge has propagated.

    Tracks orbits (reachability), stabilizers (invariance), and the Cayley
    graph (explicit transition edges).
    """
    group: PermutationGroup = field(default_factory=PermutationGroup)
    atom_ids: List[str] = field(default_factory=list)
    atom_feature_sets: Dict[str, FrozenSet[int]] = field(default_factory=dict)
    space: Optional[FeatureSpace] = None

    def act_on_atom(
        self, atom_id: str, generator_idx: int
    ) -> FrozenSet[int]:
        """Apply generator g_i to this atom's features, returning new feature set."""
        fs = self.atom_feature_sets.get(atom_id, frozenset())
        gen = self.group.generators[generator_idx]
        return gen.apply_to_set(set(fs))

    def orbit(
        self, atom_id: str, atom_pool: Dict[str, FrozenSet[int]], max_depth: int = 8
    ) -> Set[str]:
        """Compute the orbit of a knowledge atom under G (BFS on generators).

        Returns all atom IDs reachable from atom_id, including atom_id itself.
        Only includes atoms that exist in atom_pool (known knowledge atoms).
        """
        if atom_id not in self.atom_feature_sets:
            return set()

        seen = {atom_id}
        queue = [atom_id]
        fs_index: Dict[FrozenSet[int], List[str]] = defaultdict(list)
        for aid, fs in atom_pool.items():
            fs_index[fs].append(aid)

        current_depth = {atom_id: 0}
        for current in queue:
            depth = current_depth[current]
            if depth >= max_depth:
                continue
            for gi in range(self.group.n_generators()):
                new_fs = self.act_on_atom(current, gi)
                for target_id in fs_index.get(new_fs, []):
                    if target_id not in seen:
                        seen.add(target_id)
                        queue.append(target_id)
                        current_depth[target_id] = depth + 1
        return seen

    def stabilizer(self, atom_id: str) -> List[int]:
        """Return indices of generators that fix this atom.

        G_a = {g ∈ G : g·a = a} — the stabilizer subgroup generators.
        These represent transformations that preserve the atom's meaning.
        """
        fs = self.atom_feature_sets.get(atom_id, frozenset())
        fixed = []
        for gi, gen in enumerate(self.group.generators):
            if gen.apply_to_set(set(fs)) == fs:
                fixed.append(gi)
        return fixed

    def orbit_graph(
        self, atom_pool: Dict[str, FrozenSet[int]]
    ) -> Dict[str, List[Tuple[int, str]]]:
        """Build the explicit Cayley-like graph of the group action.

        Returns adjacency: atom_id -> [(generator_idx, target_atom_id), ...].
        """
        adj: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
        fs_index: Dict[FrozenSet[int], List[str]] = defaultdict(list)
        for aid, fs in atom_pool.items():
            fs_index[fs].append(aid)

        for aid in atom_pool:
            for gi in range(self.group.n_generators()):
                new_fs = self.act_on_atom(aid, gi)
                for target_id in fs_index.get(new_fs, []):
                    if target_id != aid:
                        adj[aid].append((gi, target_id))
        return dict(adj)

    def orbit_partition(
        self, atom_pool: Dict[str, FrozenSet[int]]
    ) -> List[Set[str]]:
        """Partition atom_pool into disjoint orbits under G."""
        remaining = set(atom_pool.keys())
        orbits = []
        while remaining:
            seed = remaining.pop()
            orb = self.orbit(seed, atom_pool)
            orbits.append(orb)
            remaining -= orb
        return orbits


# ─── Propagation Network Construction ─────────────────────────────────────────


def build_knowledge_atoms_from_profiles(
    profiles: List[InvariantProfile],
) -> Dict[str, KnowledgeAtom]:
    """Extract knowledge atoms from invariant profiles.

    Each profile yields atoms for its core and structural invariant itemsets.
    """
    atoms: Dict[str, KnowledgeAtom] = {}
    for p in profiles:
        for itemset in p.core_invariants:
            aid = f"{p.problem_id}:core:{'+'.join(sorted(itemset))}"
            atoms[aid] = KnowledgeAtom(
                id=aid,
                domain=p.problem_type,
                content="core invariant: " + ", ".join(sorted(itemset)),
                features=frozenset(itemset),
                atom_type="insight",
            )
        for itemset in p.structural_invariants:
            aid = f"{p.problem_id}:struct:{'+'.join(sorted(itemset))}"
            atoms[aid] = KnowledgeAtom(
                id=aid,
                domain=p.problem_type,
                content="structural invariant: " + ", ".join(sorted(itemset)),
                features=frozenset(itemset),
                atom_type="insight",
            )
        for feat in p.variable_features:
            aid = f"{p.problem_id}:var:{feat}"
            atoms[aid] = KnowledgeAtom(
                id=aid,
                domain=p.problem_type,
                content=f"variable feature: {feat}",
                features=frozenset({feat}),
                atom_type="tool",
            )
    return atoms


def build_propagation_network(
    profiles: List[InvariantProfile],
    isomorphisms: List[IsomorphismMapping],
    rules: List[TransformationRule],
    space: FeatureSpace,
) -> PropagationNetwork:
    """Build a complete knowledge propagation network.

    Combines three sources of propagation edges:
    1. Domain-internal: permutation group generators acting on atom features
    2. Cross-domain: isomorphism feature mappings as domain-crossing generators
    3. Rule-based: transformation rules as labeled generators
    """
    network = PropagationNetwork()
    network.atoms = build_knowledge_atoms_from_profiles(profiles)

    group = build_transformation_group(space, rules)

    atom_fs: Dict[str, FrozenSet[int]] = {}
    for aid, atom in network.atoms.items():
        idx_set = frozenset(
            space.feature_to_idx[f] for f in atom.features if f in space
        )
        if idx_set:
            atom_fs[aid] = idx_set

    for ri, rule in enumerate(rules):
        network.generator_names.append(rule.name)
        network.generator_descriptions.append(rule.description)

    action = GroupAction(
        group=group,
        atom_ids=list(network.atoms.keys()),
        atom_feature_sets=atom_fs,
        space=space,
    )
    network.transitions = action.orbit_graph(atom_pool=atom_fs)

    # Cross-domain edges from isomorphism feature mappings
    iso_gen_offset = len(network.generator_names)
    for ii, iso in enumerate(isomorphisms):
        gen_name = f"iso:{iso.source_domain}→{iso.target_domain}"
        network.generator_names.append(gen_name)
        network.generator_descriptions.append(
            f"Cross-domain isomorphism ({iso.isomorphism_type}, score={iso.score:.3f})"
        )
        gi = iso_gen_offset + ii

        src_atoms = [
            aid for aid, a in network.atoms.items()
            if a.domain == iso.source_domain
        ]
        tgt_atoms = [
            aid for aid, a in network.atoms.items()
            if a.domain == iso.target_domain
        ]

        for src_id in src_atoms:
            src_fs = atom_fs.get(src_id, frozenset())
            for tgt_id in tgt_atoms:
                tgt_fs = atom_fs.get(tgt_id, frozenset())
                if not src_fs or not tgt_fs:
                    continue
                src_features = {space.features[i] for i in src_fs}
                tgt_features = {space.features[i] for i in tgt_fs}
                mapped_src = set()
                for sf in src_features:
                    mapped_src.add(iso.feature_mapping.get(sf, sf))
                overlap = len(mapped_src & tgt_features)
                jaccard = overlap / max(1, len(mapped_src | tgt_features))
                if jaccard >= 0.3:
                    network.transitions.setdefault(src_id, []).append((gi, tgt_id))

    # Domain-to-domain transition paths
    domains = sorted(set(a.domain for a in network.atoms.values() if a.domain))
    for src_dom in domains:
        for tgt_dom in domains:
            if src_dom == tgt_dom:
                continue
            paths = _find_domain_transition_paths(src_dom, tgt_dom, network)
            if paths:
                network.domain_transitions[(src_dom, tgt_dom)] = paths

    return network


def _find_domain_transition_paths(
    src_domain: str,
    tgt_domain: str,
    network: PropagationNetwork,
    max_depth: int = 6,
) -> List[PropagationPath]:
    """Find all propagation paths from source domain to target domain."""
    src_atoms = [
        aid for aid, a in network.atoms.items() if a.domain == src_domain
    ]
    tgt_atoms = set(
        aid for aid, a in network.atoms.items() if a.domain == tgt_domain
    )
    if not src_atoms or not tgt_atoms:
        return []

    all_paths = []
    for src_id in src_atoms[:10]:
        paths = find_propagation_paths(
            src_id, network, target_domain=tgt_domain, max_depth=max_depth
        )
        all_paths.extend(paths)

    seen = set()
    unique = []
    for p in sorted(all_paths, key=lambda p: (p.length, -p.confidence)):
        key = (p.source_id, p.target_id)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


# ─── Propagation Path Finding ──────────────────────────────────────────────────


def find_propagation_paths(
    source_id: str,
    network: PropagationNetwork,
    target_id: Optional[str] = None,
    target_domain: Optional[str] = None,
    max_depth: int = 8,
) -> List[PropagationPath]:
    """Find shortest propagation paths via BFS on the propagation network.

    Args:
        source_id: Starting knowledge atom ID.
        network: The propagation network.
        target_id: Specific target atom (optional).
        target_domain: Target domain (optional).
        max_depth: Maximum path length.

    Returns:
        List of PropagationPath sorted by length ascending.
    """
    if source_id not in network.atoms:
        return []

    source = network.atoms[source_id]
    target_domain_atoms = None
    if target_domain:
        target_domain_atoms = set(
            aid for aid, a in network.atoms.items()
            if a.domain == target_domain
        )
        if not target_domain_atoms:
            return []

    from collections import deque
    best_paths: Dict[str, PropagationPath] = {}

    queue = deque()
    queue.append((source_id, []))
    visited_depth: Dict[str, int] = {source_id: 0}

    while queue:
        current_id, steps = queue.popleft()
        depth = len(steps)

        atom = network.atoms.get(current_id)
        if atom and current_id != source_id:
            is_target = False
            if target_id and current_id == target_id:
                is_target = True
            elif target_domain_atoms and current_id in target_domain_atoms:
                is_target = True

            if is_target and current_id not in best_paths:
                path_type = "direct" if depth == 1 else (
                    "composite" if depth <= 3 else "isomorphic"
                )
                confidence = max(0.2, 1.0 - 0.15 * (depth - 1))
                best_paths[current_id] = PropagationPath(
                    source_id=source_id,
                    target_id=current_id,
                    source_domain=source.domain,
                    target_domain=atom.domain,
                    steps=list(steps),
                    length=depth,
                    path_type=path_type,
                    confidence=round(confidence, 4),
                )
                if target_id:
                    break

        if depth >= max_depth:
            continue

        for gi, next_id in network.transitions.get(current_id, []):
            new_depth = depth + 1
            if next_id not in visited_depth or new_depth < visited_depth[next_id]:
                visited_depth[next_id] = new_depth
                gen_name = (
                    network.generator_names[gi]
                    if gi < len(network.generator_names)
                    else f"gen_{gi}"
                )
                gen_desc = (
                    network.generator_descriptions[gi]
                    if gi < len(network.generator_descriptions)
                    else ""
                )
                new_step = PropagationStep(
                    from_atom=current_id,
                    to_atom=next_id,
                    generator_idx=gi,
                    generator_name=gen_name,
                    transformation_desc=gen_desc,
                )
                queue.append((next_id, steps + [new_step]))

    result = list(best_paths.values())
    result.sort(key=lambda p: (p.length, -p.confidence))
    return result


def find_all_reachable(
    source_id: str,
    network: PropagationNetwork,
    max_depth: int = 5,
) -> Dict[int, List[str]]:
    """Find all knowledge atoms reachable from source, grouped by distance.

    Returns:
        Dict mapping distance (steps) -> list of reachable atom IDs.
    """
    if source_id not in network.atoms:
        return {}

    from collections import deque
    reachable: Dict[int, List[str]] = defaultdict(list)
    visited = {source_id}
    queue = deque([(source_id, 0)])

    while queue:
        current_id, depth = queue.popleft()
        if current_id != source_id:
            reachable[depth].append(current_id)

        if depth >= max_depth:
            continue

        for _gi, next_id in network.transitions.get(current_id, []):
            if next_id not in visited:
                visited.add(next_id)
                queue.append((next_id, depth + 1))

    return dict(reachable)


def trace_knowledge_flow(
    source_domain: str,
    target_domain: str,
    isomorphisms: List[IsomorphismMapping],
    profiles: List[InvariantProfile],
) -> Dict[str, Any]:
    """Trace how knowledge flows from source to target domain.

    Uses detected isomorphisms as bridges and group actions as internal
    propagation mechanisms.
    """
    relevant_isos = [
        iso for iso in isomorphisms
        if (iso.source_domain == source_domain and iso.target_domain == target_domain)
        or (iso.source_domain == target_domain and iso.target_domain == source_domain)
    ]

    src_profiles = [p for p in profiles if p.problem_type == source_domain]
    tgt_profiles = [p for p in profiles if p.problem_type == target_domain]

    direct_flows: List[Dict] = []
    composite_flows: List[Dict] = []
    unreachable: List[str] = []

    if not relevant_isos:
        unreachable.append(
            f"No isomorphism found between {source_domain} and {target_domain}"
        )
        return {
            "direct_flows": direct_flows,
            "composite_flows": composite_flows,
            "unreachable": unreachable,
            "flow_density": 0.0,
        }

    for iso in relevant_isos[:10]:
        flow_entry = {
            "isomorphism_type": iso.isomorphism_type,
            "score": iso.score,
            "feature_mapping": dict(iso.feature_mapping),
            "shared_core": iso.shared_core_count,
        }
        if iso.isomorphism_type in ("exact", "strong"):
            direct_flows.append(flow_entry)
        else:
            composite_flows.append(flow_entry)

    n_src_atoms = sum(
        len(p.core_invariants) + len(p.structural_invariants)
        for p in src_profiles
    )
    n_tgt_atoms = sum(
        len(p.core_invariants) + len(p.structural_invariants)
        for p in tgt_profiles
    )
    flow_density = 0.0
    if n_src_atoms > 0 and n_tgt_atoms > 0:
        total_connections = sum(
            iso.shared_core_count for iso in relevant_isos
        ) + sum(len(iso.feature_mapping) for iso in relevant_isos)
        flow_density = round(
            total_connections / (n_src_atoms * n_tgt_atoms), 4
        )

    return {
        "direct_flows": direct_flows,
        "composite_flows": composite_flows,
        "unreachable": unreachable,
        "flow_density": flow_density,
    }


def compute_propagation_stabilizer(
    atom_id: str,
    network: PropagationNetwork,
    space: FeatureSpace,
    rules: List[TransformationRule],
) -> Dict[str, Any]:
    """Analyze what properties are preserved when propagating a knowledge atom.

    The stabilizer tells us which transformations leave the atom invariant.
    """
    atom = network.atoms.get(atom_id)
    if not atom:
        return {"error": f"Atom '{atom_id}' not found"}

    group = build_transformation_group(space, rules)
    atom_fs = frozenset(
        space.feature_to_idx[f] for f in atom.features if f in space
    )

    action = GroupAction(
        group=group,
        atom_ids=[atom_id],
        atom_feature_sets={atom_id: atom_fs},
        space=space,
    )

    fixed_gens = action.stabilizer(atom_id)
    fixed_gen_names: List[str] = []
    for gi in fixed_gens:
        cumulative = 0
        for rule in rules:
            indices = [space.feature_to_idx[f] for f in rule.feature_group if f in space]
            rule_gens = max(0, len(indices) - 1)
            if cumulative <= gi < cumulative + rule_gens:
                fixed_gen_names.append(rule.name)
                break
            cumulative += rule_gens

    invariance_degree = (
        len(fixed_gens) / len(group.generators)
        if group.generators else 1.0
    )

    preserved = set()
    for gen_name in fixed_gen_names:
        for rule in rules:
            if rule.name == gen_name:
                preserved.update(rule.feature_group)
                break

    return {
        "atom_id": atom_id,
        "atom_domain": atom.domain,
        "atom_features": sorted(atom.features),
        "n_generators": len(group.generators),
        "n_fixing": len(fixed_gens),
        "invariance_degree": round(invariance_degree, 4),
        "fixing_generators": sorted(set(fixed_gen_names)),
        "preserved_properties": sorted(preserved & atom.features),
    }


# ─── Formatters ────────────────────────────────────────────────────────────────


def format_propagation_path(
    path: PropagationPath,
    network: PropagationNetwork,
    detail: bool = False,
) -> str:
    """Format a single propagation path for display."""
    source = network.atoms.get(path.source_id)
    target = network.atoms.get(path.target_id)

    src_label = source.content if source else path.source_id
    tgt_label = target.content if target else path.target_id

    lines = [
        f"## 知识传播路径: {path.source_domain} → {path.target_domain}",
        "",
        f"**源**: `{path.source_id}` ({path.source_domain})",
        f"  {src_label}",
        f"**目标**: `{path.target_id}` ({path.target_domain})",
        f"  {tgt_label}",
        "",
        f"**路径类型**: {path.path_type.upper()} | **长度**: {path.length} 步 | **置信度**: {path.confidence:.4f}",
        "",
    ]

    if path.steps:
        lines.append("### 传播步骤")
        lines.append("")
        for si, step in enumerate(path.steps, 1):
            lines.append(
                f"**{si}.** `{step.generator_name}` → `{step.to_atom}`"
            )
            if detail and step.transformation_desc:
                lines.append(f"    _{step.transformation_desc}_")
        lines.append("")

    if path.length == 1:
        lines.append("**解释**: 单步直接传播 — 源知识通过一次变换映射到目标。")
    elif path.length <= 3:
        lines.append(
            f"**解释**: 短程组合传播 ({path.length} 步) — "
            "通过两次或三次变换可达。"
        )
    else:
        lines.append(
            f"**解释**: 长程传播 ({path.length} 步) — "
            "需要多次中间变换，置信度递减。"
        )
    lines.append("")

    return "\n".join(lines)


def format_propagation_network_summary(
    network: PropagationNetwork,
) -> str:
    """Format a summary of the propagation network."""
    lines = [
        "# 知识传播网络摘要",
        "",
        f"- **知识原子数**: {len(network.atoms)}",
        f"- **传播转移数**: {sum(len(v) for v in network.transitions.values())}",
        f"- **生成器数**: {len(network.generator_names)}",
        f"- **域间转换数**: {len(network.domain_transitions)}",
        "",
    ]

    by_domain: Dict[str, int] = defaultdict(int)
    for a in network.atoms.values():
        by_domain[a.domain] += 1

    lines.append("## 各域原子分布")
    lines.append("")
    lines.append("| 域 | 原子数 |")
    lines.append("|---|---|")
    for dom, count in sorted(by_domain.items()):
        lines.append(f"| {dom} | {count} |")
    lines.append("")

    lines.append("## 生成器 (群作用)")
    lines.append("")
    lines.append("| 索引 | 名称 | 描述 |")
    lines.append("|---|---|---|")
    for gi, (name, desc) in enumerate(
        zip(network.generator_names, network.generator_descriptions)
    ):
        lines.append(f"| {gi} | `{name}` | {desc} |")
    lines.append("")

    if network.domain_transitions:
        lines.append("## 域间传播路径")
        lines.append("")
        for (src, tgt), paths in sorted(network.domain_transitions.items()):
            lines.append(f"### {src} → {tgt} ({len(paths)} 条路径)")
            for p in paths[:3]:
                lines.append(
                    f"- `{p.source_id}` → `{p.target_id}` "
                    f"({p.path_type}, {p.length} 步, conf={p.confidence:.2f})"
                )
            if len(paths) > 3:
                lines.append(f"- ... 另有 {len(paths) - 3} 条路径")
            lines.append("")

    out_degrees = [
        len(network.transitions.get(aid, [])) for aid in network.atoms
    ]
    in_degree_counts: Dict[str, int] = defaultdict(int)
    for _aid in network.atoms:
        pass
    for _src_id, edges in network.transitions.items():
        for _gi, tgt_id in edges:
            in_degree_counts[tgt_id] = in_degree_counts.get(tgt_id, 0) + 1

    lines.append("## 连通性")
    lines.append("")
    lines.append(
        f"- 平均出度: {sum(out_degrees) / max(1, len(out_degrees)):.2f}"
    )
    lines.append(f"- 孤立原子数: {sum(1 for d in out_degrees if d == 0)}")
    lines.append(f"- 最大出度: {max(out_degrees) if out_degrees else 0}")
    lines.append("")

    return "\n".join(lines)


def format_knowledge_flow(
    flow: Dict[str, Any],
    source_domain: str = "",
    target_domain: str = "",
) -> str:
    """Format a knowledge flow analysis result."""
    lines = [
        "# 知识流动分析",
        "",
    ]
    if source_domain and target_domain:
        lines.append(f"**{source_domain}** → **{target_domain}**")
        lines.append("")

    lines.extend([
        f"- **直接流**: {len(flow['direct_flows'])} 条",
        f"- **组合流**: {len(flow['composite_flows'])} 条",
        f"- **不可达**: {len(flow['unreachable'])} 条",
        f"- **流动密度**: {flow['flow_density']:.4f}",
        "",
    ])

    if flow["direct_flows"]:
        lines.append("## 直接传播流")
        lines.append("")
        for df in flow["direct_flows"][:5]:
            lines.append(
                f"- [{df['isomorphism_type']}] score={df['score']:.3f}, "
                f"shared_core={df['shared_core']}, "
                f"mapping={len(df['feature_mapping'])} pairs"
            )
        lines.append("")

    if flow["composite_flows"]:
        lines.append("## 组合传播流 (需要中间步骤)")
        lines.append("")
        for cf in flow["composite_flows"][:5]:
            lines.append(
                f"- [{cf['isomorphism_type']}] score={cf['score']:.3f}, "
                f"shared_core={cf['shared_core']}"
            )
        lines.append("")

    if flow["unreachable"]:
        lines.append("## 不可达项")
        lines.append("")
        for item in flow["unreachable"]:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def format_stabilizer_analysis(
    stabilizer_result: Dict[str, Any],
) -> str:
    """Format a stabilizer analysis for a knowledge atom."""
    if "error" in stabilizer_result:
        return f"Error: {stabilizer_result['error']}"

    lines = [
        "# 稳定化子分析 (Stabilizer Analysis)",
        "",
        f"**知识原子**: `{stabilizer_result['atom_id']}`",
        f"**域**: {stabilizer_result['atom_domain']}",
        f"**特征**: {', '.join(stabilizer_result['atom_features'])}",
        "",
        f"**不变性度**: {stabilizer_result['invariance_degree']:.4f} "
        f"({stabilizer_result['n_fixing']}/{stabilizer_result['n_generators']} "
        "个生成器固定此原子)",
        "",
    ]

    if stabilizer_result["fixing_generators"]:
        lines.append("## 保持不变的生成器")
        lines.append("")
        for name in stabilizer_result["fixing_generators"]:
            lines.append(f"- `{name}`")
        lines.append("")

    if stabilizer_result["preserved_properties"]:
        lines.append("## 传播中保留的性质")
        lines.append("")
        for prop in stabilizer_result["preserved_properties"]:
            lines.append(f"- `{prop}`")
        lines.append("")
    else:
        lines.append("> 此原子在群作用下无保留性质 — 完全可变。")
        lines.append("")

    return "\n".join(lines)
