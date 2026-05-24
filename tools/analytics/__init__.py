"""Analytics module — association rule mining, group-theoretic analysis,
and problem invariant extraction.

Provides Apriori association rules, Formal Concept Analysis (FCA), Galois
connections, equivalence classes, implication bases, lattice analysis,
problem essence recognition via Apriori + group theory fusion, cross-domain
isomorphism detection, knowledge transfer, and group action propagation
networks.

Apriori answers "what items frequently co-occur?"
Group theory (FCA) answers "what items are NECESSARILY co-present?"
Invariant extraction answers "what is the ESSENCE of this problem type?"
Isomorphism detection answers "which problems are STRUCTURALLY EQUIVALENT?"
Group action propagation answers "how does knowledge PROPAGATE across domains?"
NCD (compression distance) answers "which problems are UNIVERSALLY similar?"
"""

from tools.analytics.apriori import (
    generate_frequent_itemsets,
    generate_association_rules,
    format_rules_table,
    generate_closed_itemsets,
)
from tools.analytics.transactions import (
    extract_transactions,
    load_all_transactions,
)
from tools.analytics.recommend import (
    recommend,
    format_recommendations,
    recommend_by_closure,
    detect_knowledge_gaps,
    find_substitute_tools,
)
from tools.analytics.grouptheory import (
    FormalContext,
    FormalConcept,
    Implication,
    KnowledgeGap,
    SymmetryGroup,
    EquivalenceClass,
    object_derivation,
    attribute_derivation,
    attribute_closure,
    object_closure,
    is_closed,
    enumerate_concepts,
    build_lattice,
    find_concept_for_items,
    compute_equivalence_classes,
    detect_potential_synonyms,
    compute_implication_basis,
    validate_implication,
    detect_sublattice_gaps,
    detect_domain_analogues,
    compare_with_apriori,
    recommend_by_closure as gt_recommend_by_closure,
    analyze_comprehensively,
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
    Permutation,
    PermutationGroup,
    TransformationRule,
    OrbitDecomposition,
    InvariantProfile,
    EssenceReport,
    InvariantExtractor,
    InvariantStructureGraph,
    IsomorphismMapping,
    TransferRecipe,
    KnowledgeAtom,
    PropagationStep,
    PropagationPath,
    PropagationNetwork,
    GroupAction,
    build_transformation_group,
    build_domain_transformation_rules,
    compute_orbit_decomposition,
    build_invariant_graph,
    compute_graph_signature,
    detect_isomorphisms,
    generate_transfer_recipe,
    compare_problem_essences,
    find_analogous_problems,
    build_knowledge_atoms_from_profiles,
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
    NCDMatrix,
    NCDCluster,
    COMPRESSORS,
    compute_ncd,
    compute_ncd_text,
    ncd_matrix,
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
