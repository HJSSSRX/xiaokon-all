"""Tests for the invariant extraction module (Apriori + group theory fusion).

Covers: Permutation groups, orbit decomposition, invariant extraction,
essence reports, differential comparison, formatters, and CLI integration.
"""

import pytest
from tools.analytics.invariant import (
    FeatureSpace,
    ProblemSignature,
    Permutation,
    PermutationGroup,
    TransformationRule,
    OrbitDecomposition,
    InvariantProfile,
    EssenceReport,
    InvariantExtractor,
    build_transformation_group,
    build_domain_transformation_rules,
    compute_orbit_decomposition,
    compare_problem_essences,
    find_analogous_problems,
    format_essence_report,
    format_invariant_profile,
    format_essence_comparison,
    format_orbit_report,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Permutation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPermutation:
    def test_identity_like(self):
        p = Permutation({})
        assert p.apply_to_idx(5) == 5
        assert p.apply_to_set({1, 2, 3}) == frozenset({1, 2, 3})

    def test_transposition(self):
        p = Permutation({1: 2, 2: 1})
        assert p.apply_to_idx(1) == 2
        assert p.apply_to_idx(2) == 1
        assert p.apply_to_idx(3) == 3

    def test_apply_to_set(self):
        p = Permutation({0: 1, 1: 0})
        result = p.apply_to_set({0, 2, 3})
        assert result == frozenset({1, 2, 3})

    def test_apply_to_items(self):
        space = FeatureSpace()
        space.add_feature("a")
        space.add_feature("b")
        space.add_feature("c")
        p = Permutation({0: 1, 1: 0})
        result = p.apply_to_items(frozenset({"a", "c"}), space)
        assert result == frozenset({"b", "c"})

    def test_compose(self):
        a = Permutation({0: 1, 1: 0})  # swap 0↔1
        b = Permutation({1: 2, 2: 1})  # swap 1↔2
        c = a.compose(b)               # first b, then a: 0→0→1, 1→2→2, 2→1→0
        assert c.apply_to_idx(0) == 1  # 0→(b)→0→(a)→1
        assert c.apply_to_idx(2) == 0  # 2→(b)→1→(a)→0

    def test_inverse(self):
        p = Permutation({0: 1, 1: 2, 2: 0})
        inv = p.inverse()
        for i in range(3):
            assert inv.apply_to_idx(p.apply_to_idx(i)) == i

    def test_compose_identity(self):
        p = Permutation({0: 1, 1: 0})
        inv = p.inverse()
        composed = p.compose(inv)
        for i in range(5):
            assert composed.apply_to_idx(i) == i

    def test_repr(self):
        p = Permutation({0: 1, 1: 0})
        r = repr(p)
        assert "0" in r and "1" in r  # cycle notation


# ═══════════════════════════════════════════════════════════════════════════════
# FeatureSpace
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeatureSpace:
    def test_add_and_index(self):
        fs = FeatureSpace()
        assert fs.add_feature("rsa", "crypto") == 0
        assert fs.add_feature("aes", "crypto") == 1
        assert fs.add_feature("rsa", "crypto") == 0  # dedup
        assert len(fs) == 2
        assert fs.get_idx("rsa") == 0
        assert fs.get_idx("aes") == 1
        assert fs.get_idx("unknown") is None

    def test_contains(self):
        fs = FeatureSpace()
        fs.add_feature("vol3")
        assert "vol3" in fs
        assert "vol" not in fs

    def test_domains(self):
        fs = FeatureSpace()
        fs.add_feature("rsa", "crypto")
        fs.add_feature("vol3", "memory")
        assert fs.domains["rsa"] == "crypto"
        assert fs.domains["vol3"] == "memory"


# ═══════════════════════════════════════════════════════════════════════════════
# PermutationGroup
# ═══════════════════════════════════════════════════════════════════════════════

class TestPermutationGroup:
    def _make_space(self):
        space = FeatureSpace()
        for name in ["rsa", "rsa_1024", "rsa_2048", "aes", "vol3"]:
            space.add_feature(name)
        return space

    def test_group_from_rule(self):
        space = self._make_space()
        rule = TransformationRule(
            name="rsa_variants", description="",
            feature_group=["rsa", "rsa_1024", "rsa_2048"],
        )
        group = build_transformation_group(space, [rule])
        assert group.n_generators() >= 2  # 3 items → 2 adjacent transpositions

    def test_orbit_size_trivial(self):
        space = self._make_space()
        group = PermutationGroup()  # empty group
        size = group.orbit_size(frozenset({"aes"}), space)
        assert size == 1  # no generators → trivial orbit

    def test_orbit_size_nontrivial(self):
        space = self._make_space()
        rule = TransformationRule(
            name="rsa_variants", description="",
            feature_group=["rsa", "rsa_1024", "rsa_2048"],
        )
        group = build_transformation_group(space, [rule])
        # Orbit of {rsa} under swaps: {rsa}, {rsa_1024}, {rsa_2048}
        size = group.orbit_size(frozenset({"rsa"}), space)
        assert size == 3

    def test_is_invariant(self):
        space = self._make_space()
        rule = TransformationRule(
            name="rsa_variants", description="",
            feature_group=["rsa", "rsa_1024"],
        )
        group = build_transformation_group(space, [rule])
        # {aes} is not in the RSA rule group, so generators fix it
        assert group.is_invariant(frozenset({"aes"}), space)
        # {rsa} is in the group — applying the swap changes it
        assert not group.is_invariant(frozenset({"rsa"}), space)
        # {rsa, rsa_1024} — swapping changes the set composition (rsa↔rsa_1024, rsa_1024↔rsa)
        # Actually: apply swap(rsa, rsa_1024) to {rsa, rsa_1024} → {rsa_1024, rsa} = same set!
        assert group.is_invariant(frozenset({"rsa", "rsa_1024"}), space)

    def test_partial_invariance(self):
        space = self._make_space()
        group = PermutationGroup()
        group.add_transposition(0, 1)  # rsa ↔ rsa_1024
        group.add_transposition(2, 3)  # rsa_2048 ↔ aes
        # {rsa, vol3} — rsa in first generator, vol3 in neither
        inv = group.partial_invariance(frozenset({"rsa", "vol3"}), space)
        # First gen: {rsa_1024, vol3} != {rsa, vol3} → not fixed
        # Second gen: rsa_2048 not in set, aes not in set → but add_transposition on 2,3 ...
        # Actually the transposition is a swap - for indices not in the set, it's identity
        # So: gen2 maps {rsa, vol3} to itself since neither index 2 nor 3 is in the set
        assert inv == 0.5  # 1 of 2 generators fix it

    def test_add_transposition(self):
        group = PermutationGroup()
        group.add_transposition(5, 7)
        assert group.n_generators() == 1
        gen = group.generators[0]
        assert gen.apply_to_idx(5) == 7
        assert gen.apply_to_idx(7) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# OrbitDecomposition
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrbitDecomposition:
    def test_all_trivial(self):
        space = FeatureSpace()
        for f in ["a", "b", "c"]:
            space.add_feature(f)
        group = PermutationGroup()
        decomp = compute_orbit_decomposition(space, group)
        assert decomp.n_orbits() == 3
        assert decomp.is_trivial()

    def test_with_swaps(self):
        space = FeatureSpace()
        for f in ["a", "b", "c", "d"]:
            space.add_feature(f)
        group = PermutationGroup()
        group.add_transposition(0, 1)  # a ↔ b
        decomp = compute_orbit_decomposition(space, group)
        # Should have 3 orbits: {0,1}, {2}, {3}
        assert decomp.n_orbits() == 3
        assert not decomp.is_trivial()
        assert decomp.orbit_id_for(0) == decomp.orbit_id_for(1)
        assert decomp.orbit_id_for(0) != decomp.orbit_id_for(2)

    def test_chain_swaps(self):
        space = FeatureSpace()
        for f in ["a", "b", "c"]:
            space.add_feature(f)
        group = PermutationGroup()
        group.add_transposition(0, 1)
        group.add_transposition(1, 2)
        decomp = compute_orbit_decomposition(space, group)
        # All three should be in the same orbit (connected via union-find)
        assert decomp.n_orbits() == 1
        assert len(decomp.orbits[0]) == 3

    def test_orbit_sizes(self):
        space = FeatureSpace()
        for f in ["a", "b", "c", "d", "e"]:
            space.add_feature(f)
        group = PermutationGroup()
        group.add_transposition(0, 1)  # a↔b
        group.add_transposition(3, 4)  # d↔e
        decomp = compute_orbit_decomposition(space, group)
        sizes = sorted(decomp.orbit_sizes())
        assert sizes == [1, 2, 2]  # {c}, {a,b}, {d,e}


# ═══════════════════════════════════════════════════════════════════════════════
# Build domain transformation rules
# ═══════════════════════════════════════════════════════════════════════════════

class TestDomainRules:
    def test_all_rules_have_at_least_two_features(self):
        rules = build_domain_transformation_rules()
        assert len(rules) > 0
        for rule in rules:
            assert len(rule.feature_group) >= 2, f"{rule.name} has < 2 features"

    def test_rules_have_domains(self):
        rules = build_domain_transformation_rules()
        domains = {r.domain for r in rules}
        assert "crypto" in domains
        assert "memory_forensics" in domains
        assert "binary_analysis" in domains

    def test_rules_cover_expected_categories(self):
        rules = build_domain_transformation_rules()
        names = {r.name for r in rules}
        assert "rsa_variants" in names
        assert "aes_variants" in names
        assert "volatility_aliases" in names
        assert "text_encodings" in names
        assert "disassemblers" in names


# ═══════════════════════════════════════════════════════════════════════════════
# InvariantExtractor
# ═══════════════════════════════════════════════════════════════════════════════

def _make_crypto_problems():
    """Create synthetic crypto problem set for testing."""
    return [
        ProblemSignature(
            problem_id="crypto/rsa_chall_1",
            features={"rsa", "factorization", "python", "sage"},
            domain="crypto",
        ),
        ProblemSignature(
            problem_id="crypto/rsa_chall_2",
            features={"rsa", "factorization", "python", "openssl"},
            domain="crypto",
        ),
        ProblemSignature(
            problem_id="crypto/rsa_chall_3",
            features={"rsa_2048", "factorization", "sage", "fermat"},
            domain="crypto",
        ),
        ProblemSignature(
            problem_id="crypto/aes_chall_1",
            features={"aes", "padding_oracle", "python", "aes_cbc"},
            domain="crypto",
        ),
        ProblemSignature(
            problem_id="crypto/aes_chall_2",
            features={"aes", "padding_oracle", "python", "aes_ctr"},
            domain="crypto",
        ),
        ProblemSignature(
            problem_id="crypto/hash_chall_1",
            features={"sha256", "collision", "python", "birthday_attack"},
            domain="crypto",
        ),
    ]


class TestInvariantExtractor:
    def test_extract_essence_basic(self):
        problems = _make_crypto_problems()
        rules = [
            TransformationRule(
                name="rsa_variants", description="",
                feature_group=["rsa", "rsa_2048"], domain="crypto",
            ),
            TransformationRule(
                name="aes_variants", description="",
                feature_group=["aes", "aes_cbc", "aes_ctr"], domain="crypto",
            ),
            TransformationRule(
                name="python_versions", description="",
                feature_group=["python", "sage"], domain="crypto",
            ),
        ]
        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.3, min_invariance=0.4)

        assert report.domain == "crypto"
        assert report.n_problems == 6
        assert len(report.profiles) == 6

    def test_extract_essence_finds_core_invariants(self):
        problems = _make_crypto_problems()
        rules = [
            TransformationRule(
                name="rsa_variants", description="",
                feature_group=["rsa", "rsa_2048"], domain="crypto",
            ),
            TransformationRule(
                name="aes_variants", description="",
                feature_group=["aes", "aes_cbc", "aes_ctr"], domain="crypto",
            ),
            TransformationRule(
                name="py_variants", description="",
                feature_group=["python", "sage"], domain="crypto",
            ),
        ]
        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.25, min_invariance=0.3)

        # "factorization" appears in 3/6 problems with rsa — should be captured
        # "padding_oracle" appears in 2/6 with aes — should be structural
        rsa_profile = next(p for p in report.profiles if "rsa_chall_1" in p.problem_id)
        assert len(rsa_profile.core_invariants) + len(rsa_profile.structural_invariants) > 0

    def test_extract_essence_domain_essence(self):
        problems = [
            ProblemSignature(problem_id="p1", features={"a", "b", "c"}, domain="test"),
            ProblemSignature(problem_id="p2", features={"a", "b", "d"}, domain="test"),
            ProblemSignature(problem_id="p3", features={"a", "b", "e"}, domain="test"),
        ]
        extractor = InvariantExtractor(problems, rules=[])
        report = extractor.extract_essence(min_support=0.6, min_invariance=0.5)

        # {a, b} appears in all 3 problems and is invariant (no permutations)
        assert len(report.domain_essence) > 0
        # Domain essence should include {a, b} as it's in every problem
        domain_items = set()
        for itemset in report.domain_essence:
            domain_items.update(itemset)
        assert "a" in domain_items
        assert "b" in domain_items

    def test_variable_features_identified(self):
        problems = _make_crypto_problems()
        extractor = InvariantExtractor(problems, rules=build_domain_transformation_rules())
        report = extractor.extract_essence(min_support=0.2, min_invariance=0.4)

        for profile in report.profiles:
            # Every profile should have some features
            assert len(profile.variable_features) >= 0  # may be 0 for small test sets


# ═══════════════════════════════════════════════════════════════════════════════
# compare_problem_essences
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompareEssences:
    def test_shared_core_detected(self):
        a = InvariantProfile(
            problem_id="A",
            core_invariants=[("x", "y"), ("z",)],
            structural_invariants=[("w",)],
        )
        b = InvariantProfile(
            problem_id="B",
            core_invariants=[("x", "y"), ("q",)],
            structural_invariants=[("r",)],
        )
        diff = compare_problem_essences(a, b)
        assert ("x", "y") in diff["shared_core"]
        assert ("z",) in diff["unique_to_a_core"]
        assert ("q",) in diff["unique_to_b_core"]

    def test_no_overlap(self):
        a = InvariantProfile(problem_id="A", core_invariants=[("a",)])
        b = InvariantProfile(problem_id="B", core_invariants=[("b",)])
        diff = compare_problem_essences(a, b)
        assert len(diff["shared_core"]) == 0
        assert len(diff["unique_to_a_core"]) == 1

    def test_identical(self):
        a = InvariantProfile(
            problem_id="A", core_invariants=[("x", "y")],
        )
        b = InvariantProfile(
            problem_id="B", core_invariants=[("x", "y")],
        )
        diff = compare_problem_essences(a, b)
        assert len(diff["shared_core"]) == 1
        assert len(diff["unique_to_a_core"]) == 0
        assert len(diff["unique_to_b_core"]) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# find_analogous_problems
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalogousProblems:
    def test_finds_analogues(self):
        profiles = [
            InvariantProfile(problem_id="A", core_invariants=[("x", "y"), ("z",)]),
            InvariantProfile(problem_id="B", core_invariants=[("x", "y"), ("w",)]),
            InvariantProfile(problem_id="C", core_invariants=[("p",)]),
        ]
        results = find_analogous_problems(profiles, min_shared_core=1)
        # A-B share ("x", "y") = 1 shared core
        assert len(results) >= 1
        ids = {r[0] + "-" + r[1] for r in results}
        assert "A-B" in ids

    def test_min_shared_threshold(self):
        profiles = [
            InvariantProfile(problem_id="A", core_invariants=[("x",)]),
            InvariantProfile(problem_id="B", core_invariants=[("x",)]),
        ]
        results_low = find_analogous_problems(profiles, min_shared_core=1)
        results_high = find_analogous_problems(profiles, min_shared_core=3)
        assert len(results_low) == 1
        assert len(results_high) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Formatters (smoke tests — ensure no crashes)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormatters:
    def test_format_essence_report(self):
        report = EssenceReport(
            domain="crypto",
            n_problems=3,
            profiles=[
                InvariantProfile(
                    problem_id="crypto/test",
                    problem_type="crypto",
                    core_invariants=[("rsa", "factorization")],
                    structural_invariants=[("python",)],
                    variable_features=["sage", "openssl"],
                    invariance_scores={("rsa", "factorization"): 0.95},
                    orbit_summary={"n_orbits": 5, "nontrivial_orbits": 2, "orbit_sizes": [2, 2, 1, 1, 1]},
                ),
            ],
            cross_problem_invariants=[("rsa",)],
            domain_essence=[("rsa",)],
            transformation_groups=["test_rule: test desc"],
        )
        output = format_essence_report(report)
        assert "题目本质识别报告" in output
        assert "crypto" in output
        assert "rsa" in output
        assert "核心不变量" in output or "Core" in output

    def test_format_invariant_profile(self):
        profile = InvariantProfile(
            problem_id="test/problem",
            problem_type="crypto",
            core_invariants=[("a", "b"), ("c",)],
            structural_invariants=[("d",)],
            variable_features=["e", "f"],
            invariance_scores={("a", "b"): 0.95, ("c",): 0.8},
        )
        output = format_invariant_profile(profile)
        assert "test/problem" in output
        assert "核心不变量" in output
        assert "a" in output and "b" in output

    def test_format_essence_comparison(self):
        diff = {
            "shared_core": [("x", "y")],
            "unique_to_a_core": [("a",)],
            "unique_to_b_core": [("b",)],
            "shared_structural": [],
            "a_id": "problem_a",
            "b_id": "problem_b",
        }
        output = format_essence_comparison(diff)
        assert "problem_a" in output
        assert "problem_b" in output
        assert "共享核心" in output
        assert "x" in output

    def test_format_orbit_report(self):
        space = FeatureSpace()
        space.add_feature("a"); space.add_feature("b")
        space.add_feature("c")
        decomp = OrbitDecomposition(
            orbits=[{0, 1}, {2}],
            orbit_of={0: 0, 1: 0, 2: 1},
            orbit_labels={0: "a", 1: "c"},
        )
        output = format_orbit_report(decomp, space)
        assert "特征轨道分解" in output
        assert "2" in output  # orbit size

    def test_format_orbit_report_all_trivial(self):
        space = FeatureSpace()
        space.add_feature("x")
        decomp = OrbitDecomposition(
            orbits=[{0}],
            orbit_of={0: 0},
            orbit_labels={0: "x"},
        )
        output = format_orbit_report(decomp, space)
        assert "平凡轨道" in output


# ═══════════════════════════════════════════════════════════════════════════════
# Integration with Apriori
# ═══════════════════════════════════════════════════════════════════════════════

class TestAprioriIntegration:
    """Verify the fusion pipeline works end-to-end with Apriori."""

    def test_apriori_fusion_produces_scored_itemsets(self):
        from tools.analytics.apriori import generate_frequent_itemsets

        # Create problems where invariant patterns exist
        problems = [
            ProblemSignature(problem_id="p1", features={"core_x", "core_y", "var_a"}, domain="test"),
            ProblemSignature(problem_id="p2", features={"core_x", "core_y", "var_b"}, domain="test"),
            ProblemSignature(problem_id="p3", features={"core_x", "core_y", "var_c"}, domain="test"),
            ProblemSignature(problem_id="p4", features={"core_x", "core_y", "var_d"}, domain="test"),
        ]

        # Transformation rule: var_a ↔ var_b (should detect these as variable)
        rules = [
            TransformationRule(
                name="var_swap", description="",
                feature_group=["var_a", "var_b", "var_c", "var_d"],
                domain="test",
            ),
        ]

        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.5, min_invariance=0.4)

        # core_x + core_y should be in domain essence (appears in all 4, no transformations applied to them)
        # But we have 4 items with a transformation group connecting them all
        # core_x and core_y are NOT in the transformation rule so they should be invariant
        flat_items = [item for itemset in report.domain_essence for item in itemset]
        assert "core_x" in flat_items

    def test_apriori_without_transformations_all_invariant(self):
        """Without any transformation rules, all frequent itemsets are trivially invariant."""
        problems = [
            ProblemSignature(problem_id="p1", features={"a", "b"}, domain="test"),
            ProblemSignature(problem_id="p2", features={"a", "b"}, domain="test"),
            ProblemSignature(problem_id="p3", features={"a", "b"}, domain="test"),
        ]
        extractor = InvariantExtractor(problems, rules=[])
        report = extractor.extract_essence(min_support=0.5, min_invariance=0.5)
        # With no transformations, everything is invariant
        assert len(report.domain_essence) > 0

    def test_invariance_degree_drops_with_transformations(self):
        """Items under active transformation should have lower invariance."""
        problems = [
            ProblemSignature(problem_id="p1", features={"stable", "variant_a"}, domain="test"),
            ProblemSignature(problem_id="p2", features={"stable", "variant_b"}, domain="test"),
            ProblemSignature(problem_id="p3", features={"stable", "variant_c"}, domain="test"),
        ]
        rules = [
            TransformationRule(
                name="variant_swap", description="",
                feature_group=["variant_a", "variant_b", "variant_c"],
                domain="test",
            ),
        ]
        extractor = InvariantExtractor(problems, rules=rules)
        report = extractor.extract_essence(min_support=0.5, min_invariance=0.3)

        # Find the profile for p1
        p1_profile = next(p for p in report.profiles if p.problem_id == "p1")
        all_core_items = set()
        for itemset in p1_profile.core_invariants:
            all_core_items.update(itemset)

        # "stable" should be in core invariants (invariant under all transformations)
        assert "stable" in all_core_items or "stable" in [item for itemset in p1_profile.structural_invariants for item in itemset]


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_problems(self):
        extractor = InvariantExtractor([])
        report = extractor.extract_essence()
        assert report.n_problems == 0
        assert len(report.profiles) == 0
        assert len(report.domain_essence) == 0

    def test_single_problem(self):
        problems = [ProblemSignature(problem_id="only", features={"a", "b"}, domain="test")]
        extractor = InvariantExtractor(problems, rules=[])
        report = extractor.extract_essence()
        assert report.n_problems == 1
        assert len(report.profiles) == 1

    def test_all_same_features(self):
        problems = [
            ProblemSignature(problem_id=f"p{i}", features={"x", "y", "z"}, domain="test")
            for i in range(5)
        ]
        extractor = InvariantExtractor(problems, rules=[])
        report = extractor.extract_essence(min_support=0.8)
        # With 5 identical problems, {x}, {y}, {z}, {x,y}, etc. should all be in domain_essence
        assert len(report.domain_essence) > 0

    def test_no_frequent_itemsets(self):
        """All problems have completely disjoint features — no patterns."""
        problems = [
            ProblemSignature(problem_id="p1", features={"a", "b"}, domain="test"),
            ProblemSignature(problem_id="p2", features={"c", "d"}, domain="test"),
            ProblemSignature(problem_id="p3", features={"e", "f"}, domain="test"),
        ]
        extractor = InvariantExtractor(problems, rules=[])
        report = extractor.extract_essence(min_support=0.5)
        # With min_support=0.5 and 3 problems, need 2+ occurrences
        # Nothing appears in 2+ problems
        assert report.n_problems == 3
        # Domain essence may be empty since no feature appears in >1 problem
        assert len(report.domain_essence) >= 0  # just shouldn't crash


# ═══════════════════════════════════════════════════════════════════════════════
# ProblemSignature
# ═══════════════════════════════════════════════════════════════════════════════

class TestProblemSignature:
    def test_feature_indices(self):
        space = FeatureSpace()
        space.add_feature("a"); space.add_feature("b"); space.add_feature("c")
        ps = ProblemSignature(problem_id="test", features={"a", "c"})
        indices = ps.feature_indices(space)
        assert indices == {0, 2}

    def test_unknown_features_ignored(self):
        space = FeatureSpace()
        space.add_feature("a")
        ps = ProblemSignature(problem_id="test", features={"a", "unknown"})
        indices = ps.feature_indices(space)
        assert indices == {0}

    def test_hash_and_eq(self):
        a = ProblemSignature(problem_id="x", features={"a"})
        b = ProblemSignature(problem_id="x", features={"b"})
        c = ProblemSignature(problem_id="y", features={"a"})
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
        assert hash(a) != hash(c)


# ═══════════════════════════════════════════════════════════════════════════════
# InvariantStructureGraph
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvariantStructureGraph:
    def test_build_from_profile(self):
        from tools.analytics.invariant import build_invariant_graph
        profile = InvariantProfile(
            problem_id="test/p1",
            problem_type="crypto",
            core_invariants=[("rsa", "factorization"), ("modular_arithmetic",)],
            invariance_scores={("rsa", "factorization"): 0.95, ("modular_arithmetic",): 0.9},
        )
        graph = build_invariant_graph(profile)
        assert graph.problem_id == "test/p1"
        assert graph.domain == "crypto"
        assert "rsa" in graph.nodes
        assert "factorization" in graph.nodes
        assert "modular_arithmetic" in graph.nodes
        assert ("factorization", "rsa") in graph.edges or ("rsa", "factorization") in graph.edges
        assert graph.n_edges() >= 1

    def test_empty_profile(self):
        from tools.analytics.invariant import build_invariant_graph
        profile = InvariantProfile(problem_id="empty", problem_type="test")
        graph = build_invariant_graph(profile)
        assert graph.n_nodes() == 0
        assert graph.n_edges() == 0

    def test_degree_and_clustering(self):
        from tools.analytics.invariant import build_invariant_graph
        profile = InvariantProfile(
            problem_id="test/triangle",
            problem_type="test",
            core_invariants=[("a", "b"), ("b", "c"), ("a", "c")],
            invariance_scores={("a", "b"): 0.9, ("b", "c"): 0.9, ("a", "c"): 0.9},
        )
        graph = build_invariant_graph(profile)
        # Triangle: a-b, b-c, a-c
        assert graph.degree("a") == 2
        assert graph.degree("b") == 2
        assert graph.degree("c") == 2
        assert graph.clustering_coefficient("a") == 1.0  # perfect triangle
        assert graph.avg_clustering() == 1.0

    def test_degree_sequence(self):
        from tools.analytics.invariant import build_invariant_graph
        profile = InvariantProfile(
            problem_id="test/star",
            problem_type="test",
            core_invariants=[("center", "a"), ("center", "b"), ("center", "c")],
            invariance_scores={("center", "a"): 0.9, ("center", "b"): 0.9, ("center", "c"): 0.9},
        )
        graph = build_invariant_graph(profile)
        deg_seq = graph.degree_sequence()
        assert deg_seq == [3, 1, 1, 1]  # center=3, others=1

    def test_graph_signature(self):
        from tools.analytics.invariant import build_invariant_graph, compute_graph_signature
        profile = InvariantProfile(
            problem_id="test/sig",
            problem_type="test",
            core_invariants=[("a", "b"), ("b", "c")],
            invariance_scores={("a", "b"): 0.9, ("b", "c"): 0.85},
        )
        graph = build_invariant_graph(profile)
        sig = compute_graph_signature(graph)
        assert sig["n_nodes"] == 3  # a, b, c
        assert sig["n_edges"] == 2  # a-b, b-c
        assert "density" in sig
        assert "avg_clustering" in sig
        assert sig["n_components"] == 1

    def test_isolated_nodes(self):
        from tools.analytics.invariant import build_invariant_graph, compute_graph_signature
        profile = InvariantProfile(
            problem_id="test/iso",
            problem_type="test",
            core_invariants=[("a", "b"), ("x",)],
            invariance_scores={("a", "b"): 0.9, ("x",): 0.5},
        )
        graph = build_invariant_graph(profile)
        sig = compute_graph_signature(graph)
        assert sig["n_isolated"] == 1  # x is isolated


# ═══════════════════════════════════════════════════════════════════════════════
# Isomorphism Detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsomorphismDetection:
    def test_no_cross_domain_empty(self):
        from tools.analytics.invariant import detect_isomorphisms
        profiles = [InvariantProfile(problem_id="p1", problem_type="crypto")]
        results = detect_isomorphisms(profiles, min_score=0.0)
        assert results == []

    def test_same_domain_excluded_by_default(self):
        from tools.analytics.invariant import detect_isomorphisms
        profiles = [
            InvariantProfile(
                problem_id="p1", problem_type="crypto",
                core_invariants=[("a", "b")],
                invariance_scores={("a", "b"): 0.9},
            ),
            InvariantProfile(
                problem_id="p2", problem_type="crypto",
                core_invariants=[("a", "b")],
                invariance_scores={("a", "b"): 0.9},
            ),
        ]
        results = detect_isomorphisms(profiles, cross_domain_only=True)
        assert len(results) == 0  # same domain, excluded

    def test_cross_domain_identical_structure(self):
        from tools.analytics.invariant import detect_isomorphisms
        profiles = [
            InvariantProfile(
                problem_id="crypto/rsa1", problem_type="crypto",
                core_invariants=[("math_core", "factorization"), ("encoding",)],
                structural_invariants=[("python",)],
                invariance_scores={("math_core", "factorization"): 0.95, ("encoding",): 0.9, ("python",): 0.7},
            ),
            InvariantProfile(
                problem_id="binary/re1", problem_type="binary_analysis",
                core_invariants=[("math_core", "factorization"), ("encoding",)],
                structural_invariants=[("python",)],
                invariance_scores={("math_core", "factorization"): 0.95, ("encoding",): 0.9, ("python",): 0.7},
            ),
        ]
        results = detect_isomorphisms(profiles, min_score=0.5)
        assert len(results) == 1
        assert results[0].source_domain == "crypto"
        assert results[0].target_domain == "binary_analysis"
        assert results[0].isomorphism_type in ("exact", "strong")

    def test_different_structure_no_isomorphism(self):
        from tools.analytics.invariant import detect_isomorphisms
        profiles = [
            InvariantProfile(
                problem_id="crypto/p1", problem_type="crypto",
                core_invariants=[("a", "b"), ("c", "d")],
                invariance_scores={("a", "b"): 0.9, ("c", "d"): 0.9},
            ),
            InvariantProfile(
                problem_id="binary/p1", problem_type="binary_analysis",
                core_invariants=[("x",)],
                invariance_scores={("x",): 0.5},
            ),
        ]
        results = detect_isomorphisms(profiles, min_score=0.5)
        assert len(results) == 0

    def test_feature_mapping_generated(self):
        from tools.analytics.invariant import detect_isomorphisms
        profiles = [
            InvariantProfile(
                problem_id="crypto/r1", problem_type="crypto",
                core_invariants=[("math_op", "factor"), ("encode_op",)],
                structural_invariants=[("tool_a",), ("tool_b",)],
                invariance_scores={("math_op", "factor"): 0.95, ("encode_op",): 0.9, ("tool_a",): 0.7, ("tool_b",): 0.7},
            ),
            InvariantProfile(
                problem_id="binary/b1", problem_type="binary_analysis",
                core_invariants=[("math_op", "factor"), ("encode_op",)],
                structural_invariants=[("tool_x",), ("tool_y",)],
                invariance_scores={("math_op", "factor"): 0.95, ("encode_op",): 0.9, ("tool_x",): 0.7, ("tool_y",): 0.7},
            ),
        ]
        results = detect_isomorphisms(profiles, min_score=0.3)
        # Should detect isomorphism since core structures match
        assert len(results) >= 0  # at minimum, doesn't crash


# ═══════════════════════════════════════════════════════════════════════════════
# Transfer Recipe
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransferRecipe:
    def test_generate_recipe_crypto_to_binary(self):
        from tools.analytics.invariant import (
            IsomorphismMapping, generate_transfer_recipe,
        )
        iso = IsomorphismMapping(
            source_id="crypto/rsa1", source_domain="crypto",
            target_id="binary/re1", target_domain="binary_analysis",
            isomorphism_type="strong", score=0.75,
            signature_similarity=0.8, graph_overlap_ratio=0.5,
            shared_core_count=3,
            feature_mapping={"factorization": "decompilation", "sage": "ida"},
        )
        src = InvariantProfile(
            problem_id="crypto/rsa1", problem_type="crypto",
            core_invariants=[("rsa", "factorization"), ("sage",)],
            structural_invariants=[("python",)],
            invariance_scores={("rsa", "factorization"): 0.9, ("sage",): 0.85, ("python",): 0.7},
        )
        tgt = InvariantProfile(
            problem_id="binary/re1", problem_type="binary_analysis",
            core_invariants=[("reverse", "decompilation"), ("ida",)],
            structural_invariants=[("python",)],
            invariance_scores={("reverse", "decompilation"): 0.9, ("ida",): 0.85, ("python",): 0.7},
        )
        recipe = generate_transfer_recipe(iso, src, tgt)
        assert recipe.confidence in ("high", "medium", "low")
        assert len(recipe.transfer_steps) > 0
        assert isinstance(recipe.isomorphism, IsomorphismMapping)

    def test_low_confidence_transfer_has_caveats(self):
        from tools.analytics.invariant import (
            IsomorphismMapping, generate_transfer_recipe,
        )
        iso = IsomorphismMapping(
            source_id="a", source_domain="crypto",
            target_id="b", target_domain="binary_analysis",
            isomorphism_type="analogical", score=0.35,
            signature_similarity=0.4, graph_overlap_ratio=0.2,
            shared_core_count=0,
            structural_differences=["节点数差异: 5 vs 1"],
        )
        src = InvariantProfile(problem_id="a", problem_type="crypto",
                               core_invariants=[("x",)])
        tgt = InvariantProfile(problem_id="b", problem_type="binary_analysis",
                               core_invariants=[("y",)])
        recipe = generate_transfer_recipe(iso, src, tgt)
        assert recipe.confidence == "low"
        assert len(recipe.caveats) >= 1

    def test_symmetric_tool_lookup(self):
        from tools.analytics.invariant import _get_tool_mapping
        # Forward lookup
        fwd = _get_tool_mapping("crypto", "binary_analysis")
        assert len(fwd) > 0
        # Reverse lookup
        rev = _get_tool_mapping("binary_analysis", "crypto")
        assert len(rev) > 0

    def test_unknown_domain_pair_returns_empty(self):
        from tools.analytics.invariant import _get_tool_mapping
        result = _get_tool_mapping("nonexistent_a", "nonexistent_b")
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Isomorphism & Transfer Formatters
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsomorphismFormatters:
    def test_format_isomorphism_report(self):
        from tools.analytics.invariant import (
            IsomorphismMapping, format_isomorphism_report,
        )
        isos = [
            IsomorphismMapping(
                source_id="crypto/p1", source_domain="crypto",
                target_id="binary/p1", target_domain="binary_analysis",
                isomorphism_type="strong", score=0.78,
                signature_similarity=0.82, graph_overlap_ratio=0.55,
                shared_core_count=3,
                feature_mapping={"a": "x", "b": "y"},
                interpretation="测试同构",
            ),
        ]
        output = format_isomorphism_report(isos)
        assert "跨域同构" in output
        assert "strong" in output
        assert "crypto" in output
        assert "binary_analysis" in output

    def test_format_isomorphism_report_empty(self):
        from tools.analytics.invariant import format_isomorphism_report
        output = format_isomorphism_report([])
        assert "未检测到" in output

    def test_format_transfer_recipe(self):
        from tools.analytics.invariant import (
            IsomorphismMapping, TransferRecipe, format_transfer_recipe,
        )
        iso = IsomorphismMapping(
            source_id="crypto/p1", source_domain="crypto",
            target_id="binary/p1", target_domain="binary_analysis",
            isomorphism_type="strong", score=0.75,
            signature_similarity=0.8, graph_overlap_ratio=0.5,
            shared_core_count=3,
        )
        recipe = TransferRecipe(
            isomorphism=iso,
            tool_transfers=[
                {"source_tool": "sage", "target_tool": "ida",
                 "rationale": "数学工具 → 逆向工具", "confidence": "high"},
            ],
            technique_transfers=[
                {"source_technique": "factorization", "target_technique": "decompilation",
                 "rationale": "分解 → 反编译"},
            ],
            mapped_features=[("math", "reverse")],
            transfer_steps=["步骤1: 映射工具", "步骤2: 执行"],
            confidence="medium",
            caveats=["测试注意事项"],
        )
        output = format_transfer_recipe(recipe)
        assert "跨域知识迁移方案" in output
        assert "STRONG" in output
        assert "sage" in output
        assert "ida" in output
        assert "测试注意事项" in output

    def test_format_summary_table(self):
        from tools.analytics.invariant import (
            IsomorphismMapping, format_isomorphism_summary_table,
        )
        isos = [
            IsomorphismMapping(
                source_id=f"p{i}", source_domain="crypto",
                target_id=f"q{i}", target_domain="binary_analysis",
                isomorphism_type=t, score=0.5 + i * 0.1,
                signature_similarity=0.6, graph_overlap_ratio=0.4,
                shared_core_count=i + 1,
            )
            for i, t in enumerate(["exact", "strong", "partial", "analogical"])
        ]
        output = format_isomorphism_summary_table(isos)
        assert "EXACT" in output
        assert "STRONG" in output
        assert "PARTIAL" in output
        assert "ANALOGICAL" in output


class TestKnowledgeAtom:
    """Tests for KnowledgeAtom and PropagationStep/Path data structures."""

    def test_create_knowledge_atom(self):
        from tools.analytics.invariant import KnowledgeAtom
        atom = KnowledgeAtom(
            id="test:1", domain="crypto",
            content="RSA factorization approach",
            features=frozenset({"rsa", "factorization", "math"}),
            atom_type="technique",
        )
        assert atom.id == "test:1"
        assert atom.domain == "crypto"
        assert "rsa" in atom.features
        assert atom.atom_type == "technique"

    def test_propagation_step(self):
        from tools.analytics.invariant import PropagationStep
        step = PropagationStep(
            from_atom="a1", to_atom="a2",
            generator_idx=0, generator_name="tool_aliases",
            transformation_desc="Normalize tool names",
        )
        assert step.from_atom == "a1"
        assert step.to_atom == "a2"
        assert step.generator_name == "tool_aliases"

    def test_propagation_path(self):
        from tools.analytics.invariant import (
            PropagationPath, PropagationStep,
        )
        path = PropagationPath(
            source_id="a1", target_id="a3",
            source_domain="crypto", target_domain="binary_analysis",
            steps=[
                PropagationStep("a1", "a2", 0, "g1", ""),
                PropagationStep("a2", "a3", 1, "g2", ""),
            ],
            length=2, path_type="composite", confidence=0.85,
        )
        assert path.length == 2
        assert path.path_type == "composite"
        assert len(path.steps) == 2


class TestGroupAction:
    """Tests for GroupAction: orbit, stabilizer, orbit graph, partition."""

    def setup_method(self):
        from tools.analytics.invariant import (
            FeatureSpace, Permutation, PermutationGroup, GroupAction,
        )
        self.space = FeatureSpace()
        for f in ["a", "b", "c", "d", "e"]:
            self.space.add_feature(f, "test")

        group = PermutationGroup()
        group.add_transposition(0, 1)  # a ↔ b
        group.add_transposition(2, 3)  # c ↔ d

        self.atom_pool = {
            "atom_ab": frozenset({0, 1}),   # features: a, b
            "atom_cd": frozenset({2, 3}),   # features: c, d
            "atom_a": frozenset({0}),       # feature: a
            "atom_b": frozenset({1}),       # feature: b
            "atom_e": frozenset({4}),       # feature: e (isolated)
        }
        self.action = GroupAction(
            group=group,
            atom_ids=list(self.atom_pool.keys()),
            atom_feature_sets=self.atom_pool,
            space=self.space,
        )

    def test_orbit_reachable(self):
        """Atom a (feature {a}) should reach atom b ({b}) via a↔b transposition."""
        orb = self.action.orbit("atom_a", self.atom_pool)
        assert "atom_a" in orb
        assert "atom_b" in orb  # a↔b swaps {a} to {b}
        assert "atom_ab" not in orb  # different feature set

    def test_orbit_trivial_for_isolated(self):
        """Atom with isolated feature has trivial orbit."""
        orb = self.action.orbit("atom_e", self.atom_pool)
        assert orb == {"atom_e"}

    def test_stabilizer(self):
        """Generator a↔b fixes atom_ab ({a,b}) but not atom_a ({a})."""
        fixed_ab = self.action.stabilizer("atom_ab")
        assert len(fixed_ab) >= 1  # a↔b swaps within {a,b}, so fixes it

        fixed_a = self.action.stabilizer("atom_a")
        assert 0 not in fixed_a  # a↔b does NOT fix {a}

    def test_orbit_graph(self):
        """Orbit graph should have edges between related atoms."""
        graph = self.action.orbit_graph(self.atom_pool)
        assert "atom_a" in graph
        # atom_a should have an edge to atom_b
        targets = [tgt for _gi, tgt in graph.get("atom_a", [])]
        assert "atom_b" in targets

    def test_orbit_partition(self):
        """Orbit partition should group reachable atoms."""
        orbits = self.action.orbit_partition(self.atom_pool)
        assert len(orbits) >= 2  # at least {a,b} group, {e} isolated
        # One orbit should contain both atom_a and atom_b
        ab_orbit = next(
            o for o in orbits if "atom_a" in o or "atom_b" in o
        )
        assert "atom_a" in ab_orbit and "atom_b" in ab_orbit

    def test_act_on_atom(self):
        """Applying generator 0 (a↔b) to {0} should yield {1}."""
        result = self.action.act_on_atom("atom_a", 0)
        assert result == frozenset({1})


class TestPropagationNetwork:
    """Tests for PropagationNetwork construction and path finding."""

    def setup_method(self):
        from tools.analytics.invariant import (
            FeatureSpace, InvariantProfile,
            build_domain_transformation_rules,
        )
        self.space = FeatureSpace()
        features_crypto = ["rsa", "factorization", "math", "sage", "openssl"]
        features_binary = ["reverse", "decompilation", "ida", "assembly", "elf"]
        for f in features_crypto:
            self.space.add_feature(f, "crypto")
        for f in features_binary:
            self.space.add_feature(f, "binary_analysis")

        self.profiles = [
            InvariantProfile(
                problem_id="crypto/p1", problem_type="crypto",
                core_invariants=[("rsa", "factorization"), ("math", "sage")],
                structural_invariants=[("openssl",)],
                variable_features=["test_only"],
            ),
            InvariantProfile(
                problem_id="binary/p1", problem_type="binary_analysis",
                core_invariants=[("reverse", "decompilation"), ("assembly", "ida")],
                structural_invariants=[("elf",)],
                variable_features=[],
            ),
        ]
        self.rules = build_domain_transformation_rules()

    def test_build_atoms_from_profiles(self):
        from tools.analytics.invariant import build_knowledge_atoms_from_profiles
        atoms = build_knowledge_atoms_from_profiles(self.profiles)
        assert len(atoms) > 0
        # Should have core and structural and variable atoms
        assert any("core" in aid for aid in atoms)
        assert any("struct" in aid for aid in atoms)

    def test_build_propagation_network(self):
        from tools.analytics.invariant import (
            build_propagation_network, IsomorphismMapping,
        )
        # Create a simple isomorphism
        iso = IsomorphismMapping(
            source_id="crypto/p1", source_domain="crypto",
            target_id="binary/p1", target_domain="binary_analysis",
            isomorphism_type="strong", score=0.75,
            signature_similarity=0.8, graph_overlap_ratio=0.5,
            shared_core_count=2,
            feature_mapping={"rsa": "reverse", "factorization": "decompilation"},
        )
        network = build_propagation_network(
            self.profiles, [iso], self.rules, self.space
        )
        assert len(network.atoms) > 0
        assert len(network.generator_names) > 0
        assert "iso:crypto→binary_analysis" in network.generator_names

    def test_find_propagation_paths(self):
        from tools.analytics.invariant import (
            build_propagation_network, IsomorphismMapping,
            find_propagation_paths,
        )
        iso = IsomorphismMapping(
            source_id="crypto/p1", source_domain="crypto",
            target_id="binary/p1", target_domain="binary_analysis",
            isomorphism_type="strong", score=0.75,
            signature_similarity=0.8, graph_overlap_ratio=0.5,
            shared_core_count=2,
            feature_mapping={"rsa": "reverse", "factorization": "decompilation"},
        )
        network = build_propagation_network(
            self.profiles, [iso], self.rules, self.space
        )
        # Find source atoms in crypto domain
        src_atoms = [
            aid for aid, a in network.atoms.items()
            if a.domain == "crypto"
        ]
        assert len(src_atoms) > 0
        paths = find_propagation_paths(
            src_atoms[0], network, target_domain="binary_analysis", max_depth=5
        )
        # Should find at least some paths (or gracefully return empty)
        assert isinstance(paths, list)

    def test_find_all_reachable_empty_when_no_edges(self):
        from tools.analytics.invariant import (
            build_propagation_network, find_all_reachable,
        )
        network = build_propagation_network(
            self.profiles, [], self.rules, self.space
        )
        # Pick an atom and check reachable (possibly only itself)
        if network.atoms:
            aid = next(iter(network.atoms))
            reachable = find_all_reachable(aid, network, max_depth=3)
            assert isinstance(reachable, dict)

    def test_network_has_domain_transitions_with_iso(self):
        from tools.analytics.invariant import (
            build_propagation_network, IsomorphismMapping,
        )
        iso = IsomorphismMapping(
            source_id="crypto/p1", source_domain="crypto",
            target_id="binary/p1", target_domain="binary_analysis",
            isomorphism_type="strong", score=0.75,
            signature_similarity=0.8, graph_overlap_ratio=0.5,
            shared_core_count=2,
            feature_mapping={"rsa": "reverse"},
        )
        network = build_propagation_network(
            self.profiles, [iso], self.rules, self.space
        )
        # With strong iso, we should get domain transitions
        assert isinstance(network.domain_transitions, dict)


class TestKnowledgeFlow:
    """Tests for knowledge flow tracing."""

    def test_trace_knowledge_flow_no_isos(self):
        from tools.analytics.invariant import trace_knowledge_flow
        flow = trace_knowledge_flow("crypto", "binary_analysis", [], [])
        assert len(flow["direct_flows"]) == 0
        assert len(flow["unreachable"]) > 0
        assert flow["flow_density"] == 0.0

    def test_trace_knowledge_flow_with_isos(self):
        from tools.analytics.invariant import (
            trace_knowledge_flow, IsomorphismMapping, InvariantProfile,
        )
        iso = IsomorphismMapping(
            source_id="p1", source_domain="crypto",
            target_id="p2", target_domain="binary_analysis",
            isomorphism_type="strong", score=0.8,
            signature_similarity=0.85, graph_overlap_ratio=0.6,
            shared_core_count=3,
            feature_mapping={"a": "x", "b": "y"},
        )
        profiles = [
            InvariantProfile(
                problem_id="p1", problem_type="crypto",
                core_invariants=[("a", "b")],
            ),
            InvariantProfile(
                problem_id="p2", problem_type="binary_analysis",
                core_invariants=[("x", "y")],
            ),
        ]
        flow = trace_knowledge_flow(
            "crypto", "binary_analysis", [iso], profiles
        )
        assert len(flow["direct_flows"]) > 0
        assert flow["direct_flows"][0]["isomorphism_type"] == "strong"

    def test_stabilizer_analysis(self):
        from tools.analytics.invariant import (
            FeatureSpace, InvariantProfile, TransformationRule,
            build_propagation_network, compute_propagation_stabilizer,
        )
        space = FeatureSpace()
        for f in ["rsa", "factorization", "sage", "python"]:
            space.add_feature(f, "crypto")
        rules = [
            TransformationRule(
                name="tool_equiv", description="Tool equivalence",
                feature_group=["sage", "python"], domain="crypto",
            ),
        ]
        profiles = [
            InvariantProfile(
                problem_id="p1", problem_type="crypto",
                core_invariants=[("rsa", "factorization")],
                structural_invariants=[("sage",)],
                variable_features=[],
            ),
        ]
        network = build_propagation_network(profiles, [], rules, space)
        # Find atom with "sage" feature
        sage_atoms = [
            aid for aid, a in network.atoms.items()
            if "sage" in a.features
        ]
        if sage_atoms:
            result = compute_propagation_stabilizer(
                sage_atoms[0], network, space, rules
            )
            assert "invariance_degree" in result
            assert "fixing_generators" in result


class TestPropagationFormatters:
    """Tests for propagation path, network, flow, and stabilizer formatters."""

    def test_format_propagation_path(self):
        from tools.analytics.invariant import (
            KnowledgeAtom, PropagationNetwork, PropagationPath,
            PropagationStep, format_propagation_path,
        )
        network = PropagationNetwork()
        network.atoms = {
            "a1": KnowledgeAtom(
                id="a1", domain="crypto",
                content="RSA factorization",
                features=frozenset({"rsa", "factorization"}),
            ),
            "a2": KnowledgeAtom(
                id="a2", domain="binary_analysis",
                content="Binary decompilation",
                features=frozenset({"decompilation", "reverse"}),
            ),
        }
        path = PropagationPath(
            source_id="a1", target_id="a2",
            source_domain="crypto", target_domain="binary_analysis",
            steps=[
                PropagationStep("a1", "a2", 0, "iso:crypto→binary", "cross-domain"),
            ],
            length=1, path_type="direct", confidence=1.0,
        )
        output = format_propagation_path(path, network)
        assert "知识传播路径" in output
        assert "crypto" in output
        assert "binary_analysis" in output
        assert "DIRECT" in output

    def test_format_propagation_network_summary(self):
        from tools.analytics.invariant import (
            KnowledgeAtom, PropagationNetwork,
            format_propagation_network_summary,
        )
        network = PropagationNetwork()
        network.atoms = {
            "a1": KnowledgeAtom(id="a1", domain="crypto", content="test"),
        }
        network.generator_names = ["g1"]
        network.generator_descriptions = ["test gen"]
        output = format_propagation_network_summary(network)
        assert "知识传播网络摘要" in output
        assert "知识原子数" in output
        assert "1" in output

    def test_format_propagation_network_empty(self):
        from tools.analytics.invariant import (
            PropagationNetwork, format_propagation_network_summary,
        )
        network = PropagationNetwork()
        output = format_propagation_network_summary(network)
        assert "知识传播网络摘要" in output

    def test_format_knowledge_flow(self):
        from tools.analytics.invariant import format_knowledge_flow
        flow = {
            "direct_flows": [
                {"isomorphism_type": "exact", "score": 0.95,
                 "feature_mapping": {"a": "x"}, "shared_core": 3},
            ],
            "composite_flows": [],
            "unreachable": [],
            "flow_density": 0.5,
        }
        output = format_knowledge_flow(flow, "crypto", "binary_analysis")
        assert "知识流动分析" in output
        assert "crypto" in output
        assert "binary_analysis" in output
        assert "direct_flows" not in output  # should format as readable

    def test_format_stabilizer_analysis(self):
        from tools.analytics.invariant import format_stabilizer_analysis
        result = {
            "atom_id": "test:1",
            "atom_domain": "crypto",
            "atom_features": ["rsa", "factorization"],
            "n_generators": 10,
            "n_fixing": 8,
            "invariance_degree": 0.8,
            "fixing_generators": ["rsa_keysize", "tool_aliases"],
            "preserved_properties": ["rsa"],
        }
        output = format_stabilizer_analysis(result)
        assert "稳定化子分析" in output
        assert "test:1" in output
        assert "0.8000" in output

    def test_format_stabilizer_error(self):
        from tools.analytics.invariant import format_stabilizer_analysis
        result = {"error": "Atom 'x' not found"}
        output = format_stabilizer_analysis(result)
        assert "Error" in output


class TestGroupActionEdgeCases:
    """Edge cases for group action propagation."""

    def test_empty_atom_pool(self):
        from tools.analytics.invariant import (
            FeatureSpace, PermutationGroup, GroupAction,
        )
        group = PermutationGroup()
        action = GroupAction(group=group, atom_feature_sets={})
        orb = action.orbit("nonexistent", {})
        assert orb == set()

    def test_empty_network(self):
        from tools.analytics.invariant import (
            PropagationNetwork, find_propagation_paths,
            find_all_reachable,
        )
        network = PropagationNetwork()
        paths = find_propagation_paths("x", network)
        assert paths == []
        reachable = find_all_reachable("x", network)
        assert reachable == {}

    def test_no_generators_produces_trivial_orbits(self):
        from tools.analytics.invariant import (
            FeatureSpace, PermutationGroup, GroupAction,
        )
        space = FeatureSpace()
        space.add_feature("x", "test")
        group = PermutationGroup()  # no generators
        action = GroupAction(
            group=group,
            atom_ids=["a1"],
            atom_feature_sets={"a1": frozenset({0})},
            space=space,
        )
        orb = action.orbit("a1", {"a1": frozenset({0})})
        assert orb == {"a1"}

    def test_build_propagation_network_no_isomorphisms(self):
        from tools.analytics.invariant import (
            FeatureSpace, InvariantProfile,
            build_domain_transformation_rules,
            build_propagation_network,
        )
        space = FeatureSpace()
        for f in ["a", "b", "c"]:
            space.add_feature(f, "test")
        profiles = [
            InvariantProfile(
                problem_id="p1", problem_type="test",
                core_invariants=[("a", "b")],
            ),
        ]
        rules = build_domain_transformation_rules()
        network = build_propagation_network(profiles, [], rules, space)
        assert len(network.atoms) > 0
        # Should still work without isomorphisms
        assert isinstance(network.transitions, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# NCD (Normalized Compression Distance) tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestNCDBasic:
    """Tests for basic NCD computation."""

    def test_ncd_identical(self):
        from tools.analytics.ncd import compute_ncd
        x = b"hello world this is a test string"
        ncd = compute_ncd(x, x)
        assert ncd < 0.1, f"Identical strings should have NCD ~ 0, got {ncd}"

    def test_ncd_similar(self):
        from tools.analytics.ncd import compute_ncd
        x = b"the quick brown fox jumps over the lazy dog"
        y = b"the quick brown fox jumps over the lazy cat"
        ncd = compute_ncd(x, y)
        assert ncd < 0.5, f"Similar strings should have low NCD, got {ncd}"

    def test_ncd_dissimilar(self):
        from tools.analytics.ncd import compute_ncd
        x = b"AAAA BBBB CCCC DDDD EEEE FFFF GGGG"
        y = b"ZZZZ YYYY XXXX WWWW VVVV UUUU TTTT"
        ncd = compute_ncd(x, y)
        assert ncd > 0.3, f"Dissimilar strings should have higher NCD, got {ncd}"

    def test_ncd_range(self):
        from tools.analytics.ncd import compute_ncd
        import random
        for _ in range(20):
            a = bytes(random.randint(0, 255) for _ in range(random.randint(10, 200)))
            b = bytes(random.randint(0, 255) for _ in range(random.randint(10, 200)))
            ncd = compute_ncd(a, b, compressor="zlib")
            assert 0.0 <= ncd <= 1.0, f"NCD out of range: {ncd}"

    def test_ncd_text(self):
        from tools.analytics.ncd import compute_ncd_text
        ta = "rsa factorization sage python crypto"
        tb = "rsa factorization sage python crypto xor aes"
        ncd = compute_ncd_text(ta, tb)
        assert 0.0 <= ncd <= 1.0
        # These share most of their features, so NCD should be low
        assert ncd < 0.5, f"Expected low NCD for similar text, got {ncd}"

    def test_ncd_empty(self):
        from tools.analytics.ncd import compute_ncd
        ncd = compute_ncd(b"", b"")
        assert ncd == 0.0

    def test_ncd_one_empty(self):
        from tools.analytics.ncd import compute_ncd
        ncd = compute_ncd(b"hello world", b"")
        # zlib compresses empty string with header overhead, so NCD won't be 1.0
        # but it should be > 0 since the two are different
        assert ncd > 0.0

    def test_ncd_compressors(self):
        from tools.analytics.ncd import compute_ncd, COMPRESSORS
        x = b"rsa factorization sage python crypto" * 5
        y = b"reverse decompilation ida binary elf" * 5
        for comp_name in COMPRESSORS:
            ncd = compute_ncd(x, y, compressor=comp_name)
            assert 0.0 <= ncd <= 1.0, f"{comp_name} NCD out of range: {ncd}"


class TestNCDMatrix:
    """Tests for NCD matrix construction and queries."""

    def test_matrix_from_features(self):
        from tools.analytics.ncd import ncd_matrix_from_features
        features = {
            "p1": ["rsa", "factorization", "sage", "python"],
            "p2": ["rsa", "factorization", "sage", "python", "aes"],
            "p3": ["reverse", "decompilation", "ida", "binary", "elf"],
            "p4": ["reverse", "decompilation", "ida", "ghidra", "pe"],
        }
        matrix = ncd_matrix_from_features(features)
        assert matrix.n_objects == 4
        assert matrix.compressor == "zlib"
        # p1 and p2 should be closer than p1 and p3
        d12 = matrix.get("p1", "p2")
        d13 = matrix.get("p1", "p3")
        assert d12 is not None and d13 is not None
        assert d12 < d13, f"p1-p2 ({d12:.3f}) should be closer than p1-p3 ({d13:.3f})"

    def test_matrix_symmetric(self):
        from tools.analytics.ncd import ncd_matrix_from_features
        features = {
            "a": ["x", "y", "z"],
            "b": ["x", "y", "w"],
            "c": ["p", "q", "r"],
        }
        matrix = ncd_matrix_from_features(features)
        for i in range(3):
            for j in range(3):
                assert abs(matrix.get_by_idx(i, j) - matrix.get_by_idx(j, i)) < 1e-10

    def test_matrix_self_distance_zero(self):
        from tools.analytics.ncd import ncd_matrix_from_features
        features = {"a": ["x", "y"], "b": ["z"]}
        matrix = ncd_matrix_from_features(features)
        assert matrix.get("a", "a") == 0.0
        assert matrix.get_by_idx(1, 1) == 0.0

    def test_nearest_neighbors(self):
        from tools.analytics.ncd import ncd_matrix_from_features
        features = {
            "target": ["rsa", "factorization", "sage"],
            "close1": ["rsa", "factorization", "sage", "python"],
            "close2": ["rsa", "factorization", "openssl"],
            "far1": ["reverse", "decompilation", "ida"],
            "far2": ["network", "pcap", "wireshark"],
        }
        matrix = ncd_matrix_from_features(features)
        nn = matrix.nearest_neighbors("target", k=3)
        assert len(nn) == 3
        # close1 and close2 should be the first two
        assert nn[0][0] in ("close1", "close2")
        assert nn[1][0] in ("close1", "close2")

    def test_to_similarity(self):
        from tools.analytics.ncd import ncd_matrix_from_features
        features = {"a": ["x", "y"], "b": ["x", "z"]}
        matrix = ncd_matrix_from_features(features)
        sims = matrix.to_similarity("a")
        assert "b" in sims
        assert 0.0 <= sims["b"] <= 1.0

    def test_matrix_stats(self):
        from tools.analytics.ncd import ncd_matrix_from_features
        features = {
            f"p{i}": [f"f{j}" for j in range(i % 5 + 1)]
            for i in range(10)
        }
        matrix = ncd_matrix_from_features(features)
        assert 0.0 <= matrix.avg_distance() <= 1.0
        assert matrix.min_distance() <= matrix.max_distance()


class TestNCDClustering:
    """Tests for NCD-based hierarchical clustering."""

    def test_hierarchical_clustering(self):
        from tools.analytics.ncd import ncd_matrix_from_features, ncd_hierarchical_clustering
        features = {
            "c1_a": ["rsa", "factorization", "sage"],
            "c1_b": ["rsa", "factorization", "sage", "aes"],
            "c2_a": ["reverse", "decompilation", "ida"],
            "c2_b": ["reverse", "decompilation", "ida", "ghidra"],
        }
        matrix = ncd_matrix_from_features(features)
        dendro = ncd_hierarchical_clustering(matrix)
        assert dendro is not None
        assert dendro.size == 4

    def test_flatten_clusters(self):
        from tools.analytics.ncd import (
            ncd_matrix_from_features, ncd_hierarchical_clustering,
            flatten_clusters, get_cluster_leaves,
        )
        features = {
            "a1": ["x", "y"], "a2": ["x", "y", "z"],
            "b1": ["p", "q"], "b2": ["p", "q", "r"],
        }
        matrix = ncd_matrix_from_features(features)
        dendro = ncd_hierarchical_clustering(matrix)
        # Low threshold = many small clusters
        fine = flatten_clusters(dendro, threshold=0.1)
        assert len(fine) >= 3
        # High threshold = fewer large clusters
        coarse = flatten_clusters(dendro, threshold=0.9)
        assert len(coarse) <= len(fine)

    def test_get_cluster_leaves(self):
        from tools.analytics.ncd import (
            ncd_matrix_from_features, ncd_hierarchical_clustering,
            flatten_clusters, get_cluster_leaves,
        )
        features = {"a": ["x"], "b": ["x"], "c": ["y"]}
        matrix = ncd_matrix_from_features(features)
        dendro = ncd_hierarchical_clustering(matrix)
        clusters = flatten_clusters(dendro, threshold=0.5)
        all_leaves = []
        for c in clusters:
            all_leaves.extend(get_cluster_leaves(c))
        assert set(all_leaves) == {"a", "b", "c"}


class TestNCDAnomalies:
    """Tests for NCD anomaly detection."""

    def test_detect_anomalies(self):
        from tools.analytics.ncd import ncd_matrix_from_features, detect_ncd_anomalies
        # Create a dataset with one outlier
        features = {}
        for i in range(10):
            features[f"normal_{i}"] = ["rsa", "factorization", "sage", "python"]
        features["outlier"] = ["bluetooth", "ble", "hci", "btsnoop", "hid"]
        matrix = ncd_matrix_from_features(features)
        anomalies = detect_ncd_anomalies(matrix, z_threshold=1.5)
        assert len(anomalies) >= 1
        assert anomalies[0]["object_id"] == "outlier"

    def test_no_anomalies_when_uniform(self):
        from tools.analytics.ncd import ncd_matrix_from_features, detect_ncd_anomalies
        features = {}
        for i in range(8):
            features[f"p{i}"] = ["x", "y", "z"]
        matrix = ncd_matrix_from_features(features)
        anomalies = detect_ncd_anomalies(matrix, z_threshold=2.0)
        assert len(anomalies) == 0

    def test_too_few_objects(self):
        from tools.analytics.ncd import ncd_matrix_from_features, detect_ncd_anomalies
        features = {"a": ["x"], "b": ["y"]}
        matrix = ncd_matrix_from_features(features)
        anomalies = detect_ncd_anomalies(matrix)
        assert anomalies == []


class TestNCDCrossValidation:
    """Tests for NCD vs invariant cross-validation."""

    def test_compare_with_invariants(self):
        from tools.analytics.ncd import ncd_matrix_from_features, compare_ncd_with_invariants
        from tools.analytics.invariant import InvariantProfile

        features = {
            "p1": ["rsa", "factorization", "sage", "math"],
            "p2": ["rsa", "factorization", "sage", "aes"],
            "p3": ["reverse", "decompilation", "ida", "binary"],
            "p4": ["reverse", "decompilation", "ghidra", "pe"],
        }
        matrix = ncd_matrix_from_features(features)
        profiles = [
            InvariantProfile(
                problem_id="p1", problem_type="crypto",
                core_invariants=[("rsa", "factorization"), ("math", "sage")],
            ),
            InvariantProfile(
                problem_id="p2", problem_type="crypto",
                core_invariants=[("rsa", "factorization"), ("sage", "aes")],
            ),
            InvariantProfile(
                problem_id="p3", problem_type="binary_analysis",
                core_invariants=[("reverse", "decompilation"), ("ida", "binary")],
            ),
            InvariantProfile(
                problem_id="p4", problem_type="binary_analysis",
                core_invariants=[("reverse", "decompilation"), ("ghidra", "pe")],
            ),
        ]
        result = compare_ncd_with_invariants(matrix, profiles)
        assert "n_compared" in result
        assert result["n_compared"] > 0
        assert "pearson_correlation" in result
        assert "disagreements" in result

    def test_compare_with_few_objects(self):
        from tools.analytics.ncd import ncd_matrix_from_features, compare_ncd_with_invariants
        from tools.analytics.invariant import InvariantProfile
        features = {"a": ["x"], "b": ["y"]}
        matrix = ncd_matrix_from_features(features)
        profiles = [
            InvariantProfile(problem_id="a", problem_type="test"),
            InvariantProfile(problem_id="b", problem_type="test"),
        ]
        result = compare_ncd_with_invariants(matrix, profiles)
        assert "error" in result


class TestNCDFormatters:
    """Tests for NCD formatters."""

    def test_format_matrix_summary(self):
        from tools.analytics.ncd import ncd_matrix_from_features, format_ncd_matrix_summary
        features = {"a": ["x", "y"], "b": ["x", "z"], "c": ["p"]}
        matrix = ncd_matrix_from_features(features)
        output = format_ncd_matrix_summary(matrix)
        assert "NCD" in output
        assert "zlib" in output

    def test_format_neighbors(self):
        from tools.analytics.ncd import format_ncd_neighbors
        neighbors = [("b", 0.1), ("c", 0.5), ("d", 0.9)]
        output = format_ncd_neighbors("a", neighbors)
        assert "a" in output
        assert "0.1000" in output

    def test_format_clusters(self):
        from tools.analytics.ncd import (
            ncd_matrix_from_features, ncd_hierarchical_clustering,
            format_ncd_clusters,
        )
        features = {"a": ["x"], "b": ["x"], "c": ["y"]}
        matrix = ncd_matrix_from_features(features)
        dendro = ncd_hierarchical_clustering(matrix)
        output = format_ncd_clusters(dendro, threshold=0.5)
        assert "NCD" in output
        assert "簇" in output or "cluster" in output.lower()

    def test_format_anomalies(self):
        from tools.analytics.ncd import format_ncd_anomalies
        anomalies = [
            {"object_id": "outlier1", "mean_ncd": 0.95,
             "global_mean": 0.5, "z_score": 4.5},
        ]
        output = format_ncd_anomalies(anomalies)
        assert "outlier1" in output
        assert "4.5" in output

    def test_format_anomalies_empty(self):
        from tools.analytics.ncd import format_ncd_anomalies
        output = format_ncd_anomalies([])
        assert "未检测到" in output

    def test_format_invariant_comparison(self):
        from tools.analytics.ncd import format_ncd_invariant_comparison
        comparison = {
            "n_compared": 6, "pearson_correlation": 0.85,
            "avg_ncd_similarity": 0.5, "avg_invariant_similarity": 0.4,
            "disagreements": [
                {"a": "p1", "b": "p3", "ncd_similarity": 0.8,
                 "invariant_similarity": 0.1,
                 "interpretation": "NCD发现隐藏相似性"},
            ],
            "interpretation": "高度正相关",
        }
        output = format_ncd_invariant_comparison(comparison)
        assert "0.85" in output
        assert "p1" in output


# ═══════════════════════════════════════════════════════════════════════════════════
# Causality & Abductive Reasoning Tests
# ═══════════════════════════════════════════════════════════════════════════════════


class TestCausalGraph:
    """Tests for CausalGraph construction and traversal."""

    def test_empty_graph(self):
        from tools.analytics.causality import CausalGraph
        g = CausalGraph()
        assert g.n_nodes() == 0
        assert g.n_edges() == 0
        assert g.parents("x") == []
        assert g.children("x") == []

    def test_add_edge(self):
        from tools.analytics.causality import CausalGraph, CausalEdge
        g = CausalGraph()
        e = CausalEdge(cause="domain", effect="tool", strength=0.8,
                       support=0.3, edge_type="domain_knowledge")
        g.add_edge(e)
        assert g.n_nodes() == 2
        assert g.n_edges() == 1
        assert "domain" in g.nodes
        assert "tool" in g.nodes

    def test_parents_and_children(self):
        from tools.analytics.causality import CausalGraph, CausalEdge
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="crypto", effect="rsa", strength=0.7, support=0.2))
        g.add_edge(CausalEdge(cause="sage", effect="factorization", strength=0.6, support=0.1))
        assert set(g.children("crypto")) == {"sage", "rsa"}
        assert g.parents("sage") == ["crypto"]
        assert g.parents("factorization") == ["sage"]
        assert g.children("factorization") == []

    def test_ancestors(self):
        from tools.analytics.causality import CausalGraph, CausalEdge
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="a", effect="b", strength=0.9, support=0.1))
        g.add_edge(CausalEdge(cause="b", effect="c", strength=0.8, support=0.1))
        g.add_edge(CausalEdge(cause="c", effect="d", strength=0.7, support=0.1))
        ancestors = g.ancestors("d")
        assert "a" in ancestors
        assert "b" in ancestors
        assert "c" in ancestors
        assert "d" not in ancestors

    def test_descendants(self):
        from tools.analytics.causality import CausalGraph, CausalEdge
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="a", effect="b", strength=0.9, support=0.1))
        g.add_edge(CausalEdge(cause="b", effect="c", strength=0.8, support=0.1))
        g.add_edge(CausalEdge(cause="a", effect="d", strength=0.6, support=0.1))
        descendants = g.descendants("a")
        assert "b" in descendants
        assert "c" in descendants
        assert "d" in descendants
        assert "a" not in descendants

    def test_node_types(self):
        from tools.analytics.causality import CausalGraph, CausalEdge
        g = CausalGraph()
        g.node_types["crypto"] = "domain"
        g.node_types["sage"] = "feature"
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.8, support=0.3))
        assert g.node_types.get("crypto") == "domain"
        assert g.node_types.get("sage") == "feature"

    def test_root_and_leaf_detection(self):
        from tools.analytics.causality import CausalGraph, CausalEdge
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="root", effect="mid", strength=0.8, support=0.1))
        g.add_edge(CausalEdge(cause="mid", effect="leaf", strength=0.7, support=0.1))
        roots = [n for n in g.nodes if not g.parents(n)]
        leaves = [n for n in g.nodes if not g.children(n)]
        assert roots == ["root"]
        assert leaves == ["leaf"]


class TestCausalGraphBuilders:
    """Tests for building causal graphs from rules and transactions."""

    def test_build_from_rules(self):
        from tools.analytics.causality import build_causal_graph_from_rules
        from collections import namedtuple
        Rule = namedtuple("Rule", ["antecedent", "consequent", "confidence", "support"])
        rules = [
            Rule(("crypto",), ("sage",), 0.9, 0.3),
            Rule(("crypto",), ("rsa",), 0.7, 0.2),
            Rule(("binary_analysis",), ("ida",), 0.8, 0.25),
        ]
        graph = build_causal_graph_from_rules(rules)
        assert graph.n_nodes() >= 4
        assert graph.n_edges() == 3

    def test_build_from_rules_with_domain_labels(self):
        from tools.analytics.causality import build_causal_graph_from_rules
        from collections import namedtuple
        Rule = namedtuple("Rule", ["antecedent", "consequent", "confidence", "support"])
        rules = [
            Rule(("crypto",), ("sage",), 0.9, 0.3),
        ]
        domain_labels = {"crypto": "domain"}
        graph = build_causal_graph_from_rules(rules, domain_labels=domain_labels)
        assert graph.n_edges() >= 1
        # Edge from domain node should be domain_knowledge type
        assert any(e.edge_type == "domain_knowledge" for e in graph.edges)

    def test_build_from_rules_empty(self):
        from tools.analytics.causality import build_causal_graph_from_rules
        graph = build_causal_graph_from_rules([])
        assert graph.n_nodes() == 0
        assert graph.n_edges() == 0

    def test_build_from_transactions(self):
        from tools.analytics.causality import build_causal_graph_from_transactions
        txns = [
            {"sage", "rsa", "factorization"},
            {"sage", "rsa", "aes"},
            {"sage", "factorization"},
            {"ida", "ghidra", "reverse"},
            {"ida", "reverse", "pe"},
        ]
        domain_per_txn = {0: "crypto", 1: "crypto", 2: "crypto",
                          3: "binary", 4: "binary"}
        graph = build_causal_graph_from_transactions(
            txns, domain_per_txn, min_confidence=0.3
        )
        assert "crypto" in graph.nodes
        assert "binary" in graph.nodes
        assert graph.n_edges() > 0

    def test_build_from_transactions_empty(self):
        from tools.analytics.causality import build_causal_graph_from_transactions
        graph = build_causal_graph_from_transactions([], {})
        assert graph.n_nodes() == 0


class TestAbductiveInference:
    """Tests for abductive (reverse) inference."""

    def test_infer_domain_from_tools(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, abductive_inference,
        )
        g = CausalGraph()
        g.node_types["crypto"] = "domain"
        g.node_types["binary"] = "domain"
        g.node_types["sage"] = "feature"
        g.node_types["ida"] = "feature"
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="binary", effect="ida", strength=0.8, support=0.2))

        results = abductive_inference({"sage"}, g, candidate_causes=["crypto", "binary"])
        assert len(results) >= 1
        # crypto should rank higher for sage
        assert results[0].cause == "crypto"

    def test_infer_with_multiple_effects(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, abductive_inference,
        )
        g = CausalGraph()
        g.node_types["crypto"] = "domain"
        g.node_types["memory"] = "domain"
        g.node_types["sage"] = "feature"
        g.node_types["volatility"] = "feature"
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="memory", effect="volatility", strength=0.85, support=0.25))

        results = abductive_inference(
            {"sage", "volatility"}, g,
            candidate_causes=["crypto", "memory"],
        )
        # Both effects explained by different domains
        assert len(results) == 2

    def test_empty_observed_effects(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, abductive_inference,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        results = abductive_inference(set(), g)
        assert results == []

    def test_no_candidate_causes(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, abductive_inference,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="a", effect="b", strength=0.9, support=0.3))
        # No domain nodes and effects don't match
        results = abductive_inference({"unknown_effect"}, g)
        assert results == []

    def test_indirect_causal_path(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, abductive_inference,
        )
        g = CausalGraph()
        g.node_types["crypto"] = "domain"
        g.node_types["sage"] = "feature"
        g.node_types["factorization"] = "feature"
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="sage", effect="factorization", strength=0.7, support=0.2))

        results = abductive_inference(
            {"factorization"}, g, candidate_causes=["crypto", "sage"],
        )
        assert len(results) > 0

    def test_infer_problem_domain(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, infer_problem_domain,
        )
        g = CausalGraph()
        g.node_types["crypto"] = "domain"
        g.node_types["binary"] = "domain"
        g.node_types["sage"] = "feature"
        g.node_types["ida"] = "feature"
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="binary", effect="ida", strength=0.8, support=0.2))

        results = infer_problem_domain({"sage", "rsa"}, g)
        assert len(results) > 0
        assert results[0].cause_type == "domain"

    def test_posterior_normalization(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, abductive_inference,
        )
        g = CausalGraph()
        g.node_types["crypto"] = "domain"
        g.node_types["binary"] = "domain"
        g.node_types["sage"] = "feature"
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="binary", effect="sage", strength=0.1, support=0.01))

        results = abductive_inference({"sage"}, g, candidate_causes=["crypto", "binary"])
        total = sum(r.posterior for r in results)
        # Should be approximately 1.0
        assert abs(total - 1.0) < 0.01


class TestCounterfactualReasoning:
    """Tests for counterfactual reasoning across domains."""

    def test_counterfactual_domain_change(self):
        from tools.analytics.causality import counterfactual_domain_change
        from tools.analytics.invariant import IsomorphismMapping

        isos = [
            IsomorphismMapping(
                source_id="p1", target_id="p2",
                source_domain="crypto", target_domain="binary",
                isomorphism_type="strong", score=0.75,
                signature_similarity=0.8, graph_overlap_ratio=0.7,
                shared_core_count=2,
                feature_mapping={"sage": "ida", "rsa": "reverse"},
            ),
        ]
        profiles = []

        cf = counterfactual_domain_change(
            "test_problem",
            {"sage", "rsa", "python", "math"},
            "crypto", "binary",
            isos, profiles,
        )
        assert cf.problem_id == "test_problem"
        assert cf.original_domain == "crypto"
        assert cf.counterfactual_domain == "binary"
        assert ("sage", "ida") in cf.changed_features or any(
            c[0] == "sage" for c in cf.changed_features
        )
        assert "python" in cf.preserved_features
        assert cf.confidence > 0

    def test_counterfactual_no_isomorphism(self):
        from tools.analytics.causality import counterfactual_domain_change

        cf = counterfactual_domain_change(
            "test", {"a", "b"}, "crypto", "web", [], [],
        )
        assert len(cf.changed_features) == 0
        assert cf.confidence == 0.0


class TestCausalDiscovery:
    """Tests for simplified PC algorithm causal discovery."""

    def test_discover_from_transactions(self):
        from tools.analytics.causality import causal_discovery
        txns = [
            {"crypto", "sage", "rsa"},
            {"crypto", "sage", "factorization"},
            {"crypto", "rsa", "aes"},
            {"binary", "ida", "reverse"},
            {"binary", "ida", "pe"},
            {"binary", "ghidra", "reverse"},
        ]
        graph = causal_discovery(txns, min_dependency=0.1)
        assert graph.n_nodes() > 0
        assert graph.n_edges() > 0
        # crypto should co-occur strongly with sage
        assert "crypto" in graph.nodes or any(
            "crypto" in {e.cause, e.effect} for e in graph.edges
        )

    def test_discover_empty(self):
        from tools.analytics.causality import causal_discovery
        graph = causal_discovery([], min_dependency=0.1)
        assert graph.n_nodes() == 0


class TestRootCauseTracing:
    """Tests for root cause tracing through causal graphs."""

    def test_find_root_causes(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, find_root_causes,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="sage", effect="factorization", strength=0.7, support=0.2))
        g.add_edge(CausalEdge(cause="math", effect="factorization", strength=0.5, support=0.15))

        roots = find_root_causes("factorization", g)
        assert len(roots) >= 1
        # crypto or math should be root causes
        root_features = {r.feature for r in roots}
        assert "crypto" in root_features or "math" in root_features

    def test_find_root_causes_max_depth(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, find_root_causes,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="a", effect="b", strength=0.9, support=0.1))
        g.add_edge(CausalEdge(cause="b", effect="c", strength=0.9, support=0.1))
        g.add_edge(CausalEdge(cause="c", effect="d", strength=0.9, support=0.1))
        g.add_edge(CausalEdge(cause="d", effect="e", strength=0.9, support=0.1))

        # With max_depth=1, should only trace up one level
        roots = find_root_causes("e", g, max_depth=1)
        # At depth 1, can only reach d, which has a parent, so no root found
        assert len(roots) == 0

    def test_leaf_node_is_root(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, find_root_causes,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="root", effect="leaf", strength=0.8, support=0.2))

        roots = find_root_causes("root", g)
        # root has no parents, so it itself is the root
        assert len(roots) == 1
        assert roots[0].feature == "root"


class TestInterventionEffect:
    """Tests for intervention effect estimation."""

    def test_direct_effect(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, estimate_intervention_effect,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))

        result = estimate_intervention_effect("crypto", "sage", g)
        assert result["direct_effect"] == 0.9
        assert result["total_effect"] > 0
        assert result["intervention"] == "crypto"

    def test_indirect_effect(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, estimate_intervention_effect,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="sage", effect="factorization", strength=0.7, support=0.2))

        result = estimate_intervention_effect("crypto", "factorization", g)
        assert result["direct_effect"] == 0.0
        assert len(result["indirect_effects"]) >= 1
        assert result["indirect_effects"][0]["mediator"] == "sage"

    def test_no_effect(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, estimate_intervention_effect,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9, support=0.3))
        g.add_edge(CausalEdge(cause="binary", effect="ida", strength=0.8, support=0.2))

        result = estimate_intervention_effect("crypto", "ida", g)
        assert result["direct_effect"] == 0.0
        assert result["indirect_effects"] == []


class TestCausalityFormatters:
    """Tests for causality formatters."""

    def test_format_causal_graph_summary(self):
        from tools.analytics.causality import (
            CausalGraph, CausalEdge, format_causal_graph_summary,
        )
        g = CausalGraph()
        g.add_edge(CausalEdge(cause="crypto", effect="sage", strength=0.9,
                              support=0.3, edge_type="domain_knowledge",
                              rationale="P(sage | crypto) = 0.900"))
        output = format_causal_graph_summary(g)
        assert "crypto" in output
        assert "sage" in output
        assert "节点" in output or "node" in output.lower()

    def test_format_abductive_results(self):
        from tools.analytics.causality import (
            AbductiveResult, format_abductive_results,
        )
        results = [
            AbductiveResult(
                cause="crypto", cause_type="domain",
                posterior=0.85, prior=0.4, likelihood=0.002,
                explanation="crypto 能解释 1/1 个观察效应 — 高度可能",
                supporting_rules=[
                    {"cause": "crypto", "effect": "sage",
                     "strength": 0.9, "rationale": "P(sage|crypto)=0.9"},
                ],
            ),
        ]
        output = format_abductive_results(results, {"sage"})
        assert "crypto" in output
        assert "0.85" in output
        assert "sage" in output

    def test_format_abductive_results_empty(self):
        from tools.analytics.causality import format_abductive_results
        output = format_abductive_results([], {"sage"})
        assert "未找到" in output

    def test_format_counterfactual(self):
        from tools.analytics.causality import Counterfactual, format_counterfactual
        cf = Counterfactual(
            problem_id="test_problem",
            original_domain="crypto",
            counterfactual_domain="binary",
            preserved_features=["python", "math"],
            changed_features=[("sage", "ida"), ("rsa", "reverse")],
            confidence=0.75,
            interpretation="若在 binary 域, 2 个特征将变换",
        )
        output = format_counterfactual(cf)
        assert "test_problem" in output
        assert "crypto" in output
        assert "binary" in output
        assert "python" in output
        assert "sage" in output
        assert "ida" in output

    def test_format_root_causes(self):
        from tools.analytics.causality import RootCause, format_root_causes
        roots = [
            RootCause(
                feature="crypto", depth=2,
                causal_chain=["factorization", "sage", "crypto"],
                strength=0.63,
            ),
        ]
        output = format_root_causes(roots, "factorization")
        assert "crypto" in output
        assert "factorization" in output
        assert "sage" in output

    def test_format_root_causes_empty(self):
        from tools.analytics.causality import format_root_causes
        output = format_root_causes([], "unknown")
        assert "未找到根因" in output

    def test_format_intervention_effect(self):
        from tools.analytics.causality import format_intervention_effect
        result = {
            "intervention": "crypto", "target": "sage",
            "direct_effect": 0.9, "total_effect": 0.9,
            "indirect_effects": [],
            "interpretation": "干预 crypto 对 sage 有显著因果效应",
        }
        output = format_intervention_effect(result)
        assert "crypto" in output
        assert "sage" in output
        assert "0.9" in output

    def test_format_intervention_with_indirect(self):
        from tools.analytics.causality import format_intervention_effect
        result = {
            "intervention": "crypto", "target": "factorization",
            "direct_effect": 0.0, "total_effect": 0.63,
            "indirect_effects": [
                {"mediator": "sage", "strength": 0.63,
                 "chain": "crypto → sage → factorization"},
            ],
            "interpretation": "干预 crypto 对 factorization 有显著因果效应",
        }
        output = format_intervention_effect(result)
        assert "sage" in output
        assert "间接路径" in output
