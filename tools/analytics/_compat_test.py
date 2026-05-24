"""Compatibility test for all analytics modules — corrected API calls."""
import sys
sys.path.insert(0, ".")

passed = 0
failed = 0
errors = []

def test(name):
    def decorator(fn):
        global passed, failed
        try:
            fn()
            passed += 1
            print(f"  PASS {name}")
        except Exception as e:
            failed += 1
            msg = f"  FAIL {name}: {e}"
            print(msg)
            errors.append(msg)
    return decorator

# ── Test 1: Imports ──
print("=== Module Imports ===")

@test("import __init__")
def _():
    import tools.analytics

@test("import apriori")
def _():
    from tools.analytics.apriori import (
        generate_frequent_itemsets, generate_association_rules,
        format_rules_table, generate_closed_itemsets,
    )

@test("import transactions")
def _():
    from tools.analytics.transactions import extract_transactions, load_all_transactions

@test("import recommend")
def _():
    from tools.analytics.recommend import (
        recommend, format_recommendations, recommend_by_closure,
        detect_knowledge_gaps, find_substitute_tools,
    )

@test("import grouptheory")
def _():
    from tools.analytics.grouptheory import (
        FormalContext, FormalConcept, Implication, KnowledgeGap,
        SymmetryGroup, EquivalenceClass,
        object_derivation, attribute_derivation, attribute_closure,
        object_closure, is_closed, enumerate_concepts, build_lattice,
        find_concept_for_items, compute_equivalence_classes,
        detect_potential_synonyms, compute_implication_basis,
        validate_implication, detect_sublattice_gaps,
        detect_domain_analogues, compare_with_apriori,
        recommend_by_closure, analyze_comprehensively,
    )

@test("import invariant")
def _():
    from tools.analytics.invariant import (
        FeatureSpace, ProblemSignature, Permutation, PermutationGroup,
        TransformationRule, OrbitDecomposition, InvariantProfile,
        EssenceReport, InvariantExtractor, InvariantStructureGraph,
        IsomorphismMapping, TransferRecipe, KnowledgeAtom,
        PropagationStep, PropagationPath, PropagationNetwork, GroupAction,
        build_transformation_group, build_domain_transformation_rules,
        compute_orbit_decomposition, build_invariant_graph,
        compute_graph_signature, detect_isomorphisms,
        generate_transfer_recipe, compare_problem_essences,
        find_analogous_problems, build_knowledge_atoms_from_profiles,
        build_propagation_network, find_propagation_paths,
        find_all_reachable, trace_knowledge_flow,
        compute_propagation_stabilizer,
        get_default_domain_functor, build_transfer_natural_transformation,
        derive_tool_mapping_functorial, derive_technique_mapping_functorial,
        generate_transfer_recipe_functorial,
        SchreierSimsResult, schreier_sims,
        ConjugacyClass, ConjugacyReport, compute_conjugacy_classes,
        CharacterTable,
    )

@test("import ncd")
def _():
    from tools.analytics.ncd import (
        NCDMatrix, NCDCluster, COMPRESSORS,
        compute_ncd, compute_ncd_text, ncd_matrix,
        ncd_matrix_from_features, ncd_matrix_from_files,
        ncd_hierarchical_clustering, flatten_clusters,
        get_cluster_leaves, compare_ncd_with_invariants,
        detect_ncd_anomalies,
    )

@test("import causality")
def _():
    from tools.analytics.causality import (
        CausalEdge, CausalGraph, AbductiveResult,
        Counterfactual, RootCause,
        build_causal_graph_from_rules,
        build_causal_graph_from_transactions,
        abductive_inference, infer_problem_domain,
        counterfactual_domain_change, causal_discovery,
        find_root_causes, estimate_intervention_effect,
    )

@test("import category")
def _():
    from tools.analytics.category import (
        Object, Morphism, Category, Functor, NaturalTransformation,
        TransferTransformation, Adjunction, Monad,
        DomainCategory, FeatureCategory, DomainFunctor,
        DomainContextMonad, ProblemCategory,
        DecomposerFunctor, ComposerFunctor, SpectralResult,
        build_domain_category, build_default_domain_functor,
        build_domain_monads, build_decomposer_adjunction,
        verify_decomposition_adjunction, verify_decomposition_completeness,
        spectral_decompose, spectral_cluster, spectral_analyze_network,
    )

# ── Test 2: Apriori + FormalContext Interop ──
print("\n=== Apriori + FormalContext Interop ===")

@test("apriori with ctx.transactions")
def _():
    from tools.analytics.grouptheory import FormalContext
    from tools.analytics.apriori import generate_frequent_itemsets, generate_association_rules
    ctx = FormalContext(transactions=[{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}])
    itemsets = generate_frequent_itemsets(ctx.transactions, min_support=0.5)
    assert len(itemsets) >= 1, "should find at least 1-itemsets"
    rules = generate_association_rules(itemsets, min_confidence=0.6)
    assert isinstance(rules, list), "rules should be a list"

@test("apriori closed itemsets")
def _():
    from tools.analytics.apriori import generate_closed_itemsets
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}, {'a','b','d'}]
    closed = generate_closed_itemsets(txn, min_support=0.3)
    assert isinstance(closed, list), f"expected list, got {type(closed)}"
    if closed:
        assert isinstance(closed[0], tuple), f"expected tuple elements, got {type(closed[0])}"

@test("apriori compare_with_apriori")
def _():
    from tools.analytics.grouptheory import FormalContext, compare_with_apriori
    from tools.analytics.apriori import generate_frequent_itemsets
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}]
    ctx = FormalContext(transactions=txn)
    itemsets = generate_frequent_itemsets(txn, min_support=0.5)
    # Flatten itemsets dict to {tuple: float}
    freq_flat = {}
    for k_items in itemsets.values():
        freq_flat.update(k_items)
    result = compare_with_apriori(ctx, freq_flat)
    assert isinstance(result, dict)

# ── Test 3: Group Theory (FCA) ──
print("\n=== Group Theory (FCA) ===")

@test("FormalContext basics")
def _():
    from tools.analytics.grouptheory import (
        FormalContext, object_derivation, attribute_derivation,
        attribute_closure, object_closure, is_closed,
    )
    ctx = FormalContext(transactions=[{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}])
    assert ctx.n_transactions == 4
    assert ctx.n_items == 3

    # object_derivation takes Set[str] (items), returns Set[int] (object indices)
    obj_der = object_derivation(ctx, {'a', 'b'})
    assert isinstance(obj_der, set)

    # attribute_derivation takes Set[int] (object indices), returns Set[str] (items)
    attr_der = attribute_derivation(ctx, {0, 1})
    assert isinstance(attr_der, set)

    closed = attribute_closure(ctx, {'b'})
    assert isinstance(closed, set)

    c = is_closed(ctx, {'a', 'b', 'c'})
    assert isinstance(c, bool)

@test("enumerate_concepts")
def _():
    from tools.analytics.grouptheory import FormalContext, enumerate_concepts
    ctx = FormalContext(transactions=[{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}])
    concepts = enumerate_concepts(ctx, min_support=1)
    assert len(concepts) > 0

@test("build_lattice")
def _():
    from tools.analytics.grouptheory import FormalContext, build_lattice
    ctx = FormalContext(transactions=[{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}])
    lattice = build_lattice(ctx, min_support=1)
    assert 'concepts' in lattice
    assert lattice['concept_count'] > 0

@test("compute_implication_basis")
def _():
    from tools.analytics.grouptheory import FormalContext, compute_implication_basis
    ctx = FormalContext(transactions=[{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}])
    basis = compute_implication_basis(ctx, min_support=1)
    assert isinstance(basis, list)

@test("detect_sublattice_gaps")
def _():
    from tools.analytics.grouptheory import FormalContext, detect_sublattice_gaps
    ctx = FormalContext(transactions=[{'a','b'}, {'b','c'}, {'a','c'}])
    gaps = detect_sublattice_gaps(ctx, max_size=4)
    assert isinstance(gaps, list)

@test("compute_equivalence_classes")
def _():
    from tools.analytics.grouptheory import FormalContext, compute_equivalence_classes
    ctx = FormalContext(transactions=[{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}])
    eq = compute_equivalence_classes(ctx)
    assert isinstance(eq, list)

# ── Test 4: Invariant (Group Theory + Apriori Fusion) ──
print("\n=== Invariant (Group Theory + Apriori Fusion) ===")

@test("Permutation basics")
def _():
    from tools.analytics.invariant import Permutation, PermutationGroup
    p1 = Permutation({'a':'b', 'b':'a', 'c':'c'})
    p2 = Permutation({'a':'a', 'b':'c', 'c':'b'})
    group = PermutationGroup([p1, p2])
    assert len(group.generators) == 2
    # PermutationGroup doesn't have order(), use schreier_sims for that

@test("InvariantExtractor with ProblemSignature")
def _():
    from tools.analytics.invariant import InvariantExtractor, ProblemSignature, FeatureSpace
    space = FeatureSpace()
    space.register('a'); space.register('b'); space.register('c')
    sigs = [
        ProblemSignature(problem_id="p1", features={'a','b'}, domain="test"),
        ProblemSignature(problem_id="p2", features={'b','c'}, domain="test"),
        ProblemSignature(problem_id="p3", features={'a','c'}, domain="test"),
    ]
    extractor = InvariantExtractor(problems=sigs, space=space)
    assert extractor.n_problems == 3

@test("InvariantExtractor extract")
def _():
    from tools.analytics.invariant import InvariantExtractor, ProblemSignature, FeatureSpace
    space = FeatureSpace()
    space.register('a'); space.register('b'); space.register('c')
    sigs = [
        ProblemSignature(problem_id="p1", features={'a','b','c'}, domain="test"),
        ProblemSignature(problem_id="p2", features={'a','b'}, domain="test"),
        ProblemSignature(problem_id="p3", features={'a','c'}, domain="test"),
    ]
    extractor = InvariantExtractor(problems=sigs, space=space)
    profile = extractor.extract()
    assert profile is not None

@test("build_transformation_group")
def _():
    from tools.analytics.invariant import (
        build_transformation_group, ProblemSignature, FeatureSpace,
    )
    space = FeatureSpace()
    for f in ['a','b','c','d']:
        space.register(f)
    sigs = [
        ProblemSignature(problem_id="p1", features={'a','b'}, domain="test"),
        ProblemSignature(problem_id="p2", features={'c','d'}, domain="test"),
    ]
    group = build_transformation_group(sigs, space)
    assert group is not None

@test("detect_isomorphisms")
def _():
    from tools.analytics.invariant import (
        detect_isomorphisms, ProblemSignature, FeatureSpace,
    )
    space_a = FeatureSpace()
    space_b = FeatureSpace()
    for f in ['x','y','z']:
        space_a.register(f)
        space_b.register(f)
    sigs_a = [
        ProblemSignature(problem_id="a1", features={'x','y'}, domain="dom_a"),
        ProblemSignature(problem_id="a2", features={'x','z'}, domain="dom_a"),
    ]
    sigs_b = [
        ProblemSignature(problem_id="b1", features={'x','y'}, domain="dom_b"),
        ProblemSignature(problem_id="b2", features={'x','z'}, domain="dom_b"),
    ]
    isos = detect_isomorphisms(sigs_a, sigs_b, space_a, space_b)
    assert isinstance(isos, list)

# ── Test 5: Schreier-Sims ──
print("\n=== Schreier-Sims Algorithm ===")

@test("schreier_sims S_3")
def _():
    from tools.analytics.invariant import (
        Permutation, PermutationGroup, schreier_sims, FeatureSpace,
    )
    space = FeatureSpace()
    for f in ['a','b','c']:
        space.register(f)
    r = Permutation({'a':'b', 'b':'c', 'c':'a'})
    s = Permutation({'a':'b', 'b':'a', 'c':'c'})
    group = PermutationGroup([r, s], space)
    result = schreier_sims(group, n_points=3)
    assert result.order == 6, f"expected 6, got {result.order}"
    assert len(result.base) > 0

@test("schreier_sims member test")
def _():
    from tools.analytics.invariant import (
        Permutation, PermutationGroup, schreier_sims, FeatureSpace,
    )
    space = FeatureSpace()
    for f in ['a','b','c']:
        space.register(f)
    r = Permutation({'a':'b', 'b':'c', 'c':'a'})
    s = Permutation({'a':'b', 'b':'a', 'c':'c'})
    group = PermutationGroup([r, s], space)
    result = schreier_sims(group, n_points=3)
    assert result.member(r), "3-cycle should be in S_3"
    assert result.member(Permutation({})), "identity should be in S_3"

@test("schreier_sims trivial group")
def _():
    from tools.analytics.invariant import Permutation, PermutationGroup, schreier_sims
    id_group = PermutationGroup([Permutation({})])
    result = schreier_sims(id_group, n_points=1)
    assert result.order == 1

# ── Test 6: Conjugacy Classes ──
print("\n=== Conjugacy Classes ===")

@test("compute_conjugacy_classes S_3")
def _():
    from tools.analytics.invariant import (
        Permutation, PermutationGroup, compute_conjugacy_classes, FeatureSpace,
    )
    space = FeatureSpace()
    for f in ['a','b','c']:
        space.register(f)
    r = Permutation({'a':'b', 'b':'c', 'c':'a'})
    s = Permutation({'a':'b', 'b':'a', 'c':'c'})
    group = PermutationGroup([r, s], space)
    report = compute_conjugacy_classes(group, n_points=3)
    assert report.total_elements > 0
    assert len(report.classes) > 0

# ── Test 7: Character Theory ──
print("\n=== Character Theory ===")

@test("CharacterTable S_3")
def _():
    from tools.analytics.invariant import (
        Permutation, PermutationGroup, CharacterTable,
        compute_conjugacy_classes, FeatureSpace,
    )
    space = FeatureSpace()
    for f in ['a','b','c']:
        space.register(f)
    r = Permutation({'a':'b', 'b':'c', 'c':'a'})
    s = Permutation({'a':'b', 'b':'a', 'c':'c'})
    group = PermutationGroup([r, s], space)
    conj = compute_conjugacy_classes(group, n_points=3)
    ct = CharacterTable.from_conjugacy(conj, group)
    assert ct.n_classes > 0

# ── Test 8: Category Theory ──
print("\n=== Category Theory ===")

@test("build_domain_category")
def _():
    from tools.analytics.category import build_domain_category
    cat = build_domain_category()
    assert cat.name == "DomainCategory"
    assert len(cat.objects) >= 2

@test("build_default_domain_functor")
def _():
    from tools.analytics.category import build_domain_category, build_default_domain_functor
    cat = build_domain_category()
    F = build_default_domain_functor(cat)
    assert F is not None

@test("build_domain_monads")
def _():
    from tools.analytics.category import build_domain_monads
    monads = build_domain_monads()
    assert isinstance(monads, dict)
    assert len(monads) > 0

@test("build_decomposer_adjunction")
def _():
    from tools.analytics.category import build_decomposer_adjunction
    F, G, adj = build_decomposer_adjunction()
    assert F is not None
    assert G is not None
    assert adj is not None

@test("verify_decomposition_adjunction")
def _():
    from tools.analytics.category import (
        build_decomposer_adjunction, verify_decomposition_adjunction,
    )
    F, G, adj = build_decomposer_adjunction()
    test_problems = [{"id": "test1", "goal": "analyze memory"}]
    ok, messages = verify_decomposition_adjunction(
        F.map_object, G.map_object, test_problems
    )
    assert isinstance(ok, bool)

@test("spectral_decompose")
def _():
    from tools.analytics.category import spectral_decompose
    # Simple 4-node graph adjacency matrix
    adj = [
        [0.0, 1.0, 0.0, 0.0],
        [1.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
    ]
    result = spectral_decompose(adj)
    assert len(result.eigenvalues) > 0
    assert len(result.eigenvectors) > 0

@test("spectral_cluster")
def _():
    from tools.analytics.category import spectral_decompose, spectral_cluster
    adj = [
        [0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        [1.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0, 1.0],
        [0.0, 0.0, 0.0, 1.0, 0.0, 1.0],
        [0.0, 0.0, 0.0, 1.0, 1.0, 0.0],
    ]
    spec = spectral_decompose(adj)
    clusters = spectral_cluster(spec, k=2)
    assert len(clusters) == 6  # one label per node
    # Should find two clusters
    assert len(set(clusters)) == 2

# ── Test 9: Functorial Integration (invariant.py additions) ──
print("\n=== Functorial Integration ===")

@test("get_default_domain_functor")
def _():
    from tools.analytics.invariant import get_default_domain_functor
    F = get_default_domain_functor()
    assert F is not None

@test("derive_tool_mapping_functorial")
def _():
    from tools.analytics.invariant import derive_tool_mapping_functorial
    result = derive_tool_mapping_functorial("forensics", "network")
    assert isinstance(result, dict)

@test("derive_technique_mapping_functorial")
def _():
    from tools.analytics.invariant import derive_technique_mapping_functorial
    result = derive_technique_mapping_functorial("forensics", "network")
    assert isinstance(result, dict)

@test("generate_transfer_recipe_functorial")
def _():
    from tools.analytics.invariant import (
        generate_transfer_recipe_functorial, IsomorphismMapping,
        ProblemSignature, FeatureSpace, InvariantExtractor,
    )
    space = FeatureSpace()
    for f in ['x','y','z']:
        space.register(f)
    sigs_src = [ProblemSignature(problem_id="s1", features={'x','y'}, domain="dom_a")]
    sigs_tgt = [ProblemSignature(problem_id="t1", features={'x','z'}, domain="dom_b")]
    iso = IsomorphismMapping(
        source_domain="dom_a", target_domain="dom_b",
        feature_mapping={'x':'x', 'y':'z'},
        structure_score=0.9,
    )
    extractor_src = InvariantExtractor(problems=sigs_src, space=space)
    profile_src = extractor_src.extract()
    recipe = generate_transfer_recipe_functorial(
        iso, source_profile=profile_src, source_features={'x','y'}
    )
    assert recipe is not None

# ── Test 10: NCD ──
print("\n=== NCD ===")

@test("compute_ncd basic")
def _():
    from tools.analytics.ncd import compute_ncd
    d = compute_ncd(b"hello world", b"hello there")
    assert 0.0 <= d <= 2.0

@test("ncd_matrix")
def _():
    from tools.analytics.ncd import ncd_matrix
    objects = {
        "a": b"hello world",
        "b": b"hello there",
        "c": b"goodbye world",
        "d": b"goodbye there",
    }
    matrix = ncd_matrix(objects)
    assert matrix.n == 4

@test("ncd_hierarchical_clustering")
def _():
    from tools.analytics.ncd import ncd_matrix, ncd_hierarchical_clustering
    objects = {
        "a": b"hello world",
        "b": b"hello there",
        "c": b"goodbye world",
        "d": b"goodbye there",
        "e": b"foo bar",
    }
    matrix = ncd_matrix(objects)
    clusters = ncd_hierarchical_clustering(matrix, n_clusters=2)
    assert len(clusters) > 0

# ── Test 11: Causality ──
print("\n=== Causality ===")

@test("build_causal_graph_from_transactions")
def _():
    from tools.analytics.causality import build_causal_graph_from_transactions
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}]
    g = build_causal_graph_from_transactions(txn, min_confidence=0.5)
    assert g is not None

@test("causal_discovery")
def _():
    from tools.analytics.causality import causal_discovery
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}, {'a','b','d'}]
    g = causal_discovery(txn, min_dependency=0.2)
    assert g is not None

@test("abductive_inference")
def _():
    from tools.analytics.causality import (
        build_causal_graph_from_transactions, abductive_inference,
    )
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}]
    g = build_causal_graph_from_transactions(txn, min_confidence=0.5)
    results = abductive_inference(g, {'c'}, top_k=3)
    assert isinstance(results, list)

@test("find_root_causes")
def _():
    from tools.analytics.causality import (
        build_causal_graph_from_transactions, find_root_causes,
    )
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}]
    g = build_causal_graph_from_transactions(txn, min_confidence=0.5)
    roots = find_root_causes(g, {'c'}, max_depth=3)
    assert isinstance(roots, list)

@test("counterfactual_domain_change")
def _():
    from tools.analytics.causality import counterfactual_domain_change
    cf = counterfactual_domain_change(
        problem_id="test1",
        source_features={'dd'},
        source_domain="forensics",
        target_domain="network",
        isomorphisms=[],
        profiles=[],
    )
    assert cf is not None

@test("estimate_intervention_effect")
def _():
    from tools.analytics.causality import (
        build_causal_graph_from_transactions, estimate_intervention_effect,
    )
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}]
    g = build_causal_graph_from_transactions(txn, min_confidence=0.5)
    effect = estimate_intervention_effect(g, 'a', 'c')
    assert isinstance(effect, dict)

# ── Test 12: Cross-module interop ──
print("\n=== Cross-Module Interop ===")

@test("FCA + Apriori + Invariant pipeline")
def _():
    from tools.analytics.grouptheory import FormalContext, enumerate_concepts, build_lattice
    from tools.analytics.apriori import generate_frequent_itemsets
    from tools.analytics.invariant import (
        ProblemSignature, FeatureSpace, InvariantExtractor,
    )
    # 1. Real transactions -> FormalContext
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}, {'a','b'}, {'c'}]
    ctx = FormalContext(transactions=txn)
    # 2. FCA
    concepts = enumerate_concepts(ctx, min_support=2)
    lattice = build_lattice(ctx, min_support=2)
    # 3. Apriori
    itemsets = generate_frequent_itemsets(txn, min_support=0.4)
    # 4. Invariant extraction
    space = FeatureSpace()
    for item in ctx.items:
        space.register(item)
    sigs = [
        ProblemSignature(problem_id=f"p{i}", features=set(t), domain="test")
        for i, t in enumerate(txn)
    ]
    extractor = InvariantExtractor(problems=sigs, space=space)
    profile = extractor.extract()
    # All should succeed
    assert len(concepts) > 0
    assert lattice['concept_count'] > 0
    assert len(itemsets) > 0
    assert profile is not None

@test("Category + Invariant interop")
def _():
    from tools.analytics.category import build_domain_category, build_default_domain_functor
    from tools.analytics.invariant import get_default_domain_functor
    cat = build_domain_category()
    F1 = build_default_domain_functor(cat)
    F2 = get_default_domain_functor()
    # Both should return valid functors
    assert F1 is not None
    assert F2 is not None

@test("Causality + FCA interop")
def _():
    from tools.analytics.causality import build_causal_graph_from_transactions
    from tools.analytics.grouptheory import FormalContext, enumerate_concepts
    txn = [{'a','b'}, {'b','c'}, {'a','c'}, {'a','b','c'}]
    ctx = FormalContext(transactions=txn)
    g = build_causal_graph_from_transactions(txn, min_confidence=0.5)
    concepts = enumerate_concepts(ctx, min_support=2)
    assert g is not None
    assert len(concepts) > 0

# ── Test 13: Edge cases ──
print("\n=== Edge Cases ===")

@test("empty transactions")
def _():
    from tools.analytics.grouptheory import FormalContext, enumerate_concepts
    from tools.analytics.apriori import generate_frequent_itemsets
    ctx = FormalContext(transactions=[])
    assert ctx.n_transactions == 0
    itemsets = generate_frequent_itemsets([], min_support=0.5)
    assert itemsets == {}

@test("single item transactions")
def _():
    from tools.analytics.grouptheory import FormalContext, enumerate_concepts
    from tools.analytics.apriori import generate_frequent_itemsets
    txn = [{'a'}, {'b'}, {'a'}]
    ctx = FormalContext(transactions=txn)
    concepts = enumerate_concepts(ctx, min_support=1)
    assert len(concepts) > 0
    itemsets = generate_frequent_itemsets(txn, min_support=0.5)
    assert len(itemsets) >= 1

@test("no common items")
def _():
    from tools.analytics.grouptheory import FormalContext, enumerate_concepts
    txn = [{'a','b'}, {'c','d'}, {'e','f'}]
    ctx = FormalContext(transactions=txn)
    concepts = enumerate_concepts(ctx, min_support=1)
    assert len(concepts) > 0

# ── Summary ──
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed out of {passed+failed} tests")
if errors:
    print("Failures:")
    for e in errors:
        print(f"  {e}")
sys.exit(0 if failed == 0 else 1)
