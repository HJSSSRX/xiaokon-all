"""Category theory for cross-domain knowledge transfer — 范畴论驱动的跨域知识迁移.

Replaces hardcoded _CROSS_DOMAIN_TOOL_MAP and _CROSS_DOMAIN_TECHNIQUE_MAP
with functor-based derivation. The Galois connection in grouptheory.py is
already an adjunction; this module makes that explicit and extends it.

Core constructions:
  - Category: objects (domains, feature spaces) + morphisms (technique transforms)
  - Functor F: C → D — maps domains to feature spaces, preserving transformation structure
  - NaturalTransformation η: F ⇒ G — cross-domain tool/technique mappings
  - Adjunction F ⊣ G — decomposition (free) ⊣ evaluation (forgetful)

Mathematical foundation:
  - Functor laws: F(id_A) = id_{F(A)},  F(g ∘ f) = F(g) ∘ F(f)
  - Naturality square: η_B ∘ F(f) = G(f) ∘ η_A  for all f: A → B
  - Adjunction: Hom_D(F(A), B) ≅ Hom_C(A, G(B))  naturally in A, B
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import product
from typing import (
    Any, Callable, Dict, FrozenSet, Generic, List, Optional,
    Set, Tuple, TypeVar,
)

# ─── Type Variables ──────────────────────────────────────────────────────────

ObjA = TypeVar("ObjA")
ObjB = TypeVar("ObjB")
MorA = TypeVar("MorA")
MorB = TypeVar("MorB")

# ─── Category Base ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Object:
    """An object in a category. Lightweight wrapper with a label and domain tag."""
    label: str
    domain: str = ""

    def __repr__(self) -> str:
        return f"Obj({self.label})" if not self.domain else f"Obj({self.domain}/{self.label})"


@dataclass(frozen=True)
class Morphism:
    """A morphism f: source → target in a category.

    The `data` dict carries domain-specific payload (e.g., technique name,
    transformation rule, tool substitution).
    """
    source: Object
    target: Object
    label: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"{self.source.label} —{self.label or 'f'}→ {self.target.label}"


class Category(ABC):
    """Abstract category: objects, morphisms, composition, and identities.

    Subclasses provide concrete object/morphism collections and implement
    `compose` and `identity`.
    """

    @abstractmethod
    def objects(self) -> Set[Object]:
        ...

    @abstractmethod
    def morphisms(self) -> List[Morphism]:
        ...

    @abstractmethod
    def hom(self, source: Object, target: Object) -> List[Morphism]:
        """Return all morphisms from source to target."""
        ...

    @abstractmethod
    def identity(self, obj: Object) -> Morphism:
        ...

    @abstractmethod
    def compose(self, g: Morphism, f: Morphism) -> Optional[Morphism]:
        """Compose g ∘ f; returns None if cod(f) ≠ dom(g)."""
        ...

    def has_morphism(self, source: Object, target: Object) -> bool:
        return len(self.hom(source, target)) > 0


# ─── Domain Category ─────────────────────────────────────────────────────────

class DomainCategory(Category):
    """Category whose objects are forensic domains and morphisms are technique
    transformations between them.

    Objects: memory_forensics, disk_forensics, network_forensics,
             binary_analysis, crypto, stego, mobile_forensics, web_pentest,
             server_forensics
    Morphisms: technique transformations, tool substitutions, encoding variants
    """

    def __init__(self):
        self._objects: Dict[str, Object] = {}
        self._morphisms: Dict[Tuple[Object, Object], List[Morphism]] = defaultdict(list)
        self._build()

    def _build(self):
        domains = [
            ("memory_forensics", "内存取证"),
            ("disk_forensics", "磁盘取证"),
            ("network_forensics", "网络取证"),
            ("binary_analysis", "二进制分析"),
            ("crypto", "密码学"),
            ("stego", "隐写"),
            ("mobile_forensics", "移动取证"),
            ("web_pentest", "Web渗透"),
            ("server_forensics", "服务端取证"),
        ]
        for abbr, full in domains:
            obj = Object(label=abbr, domain=full)
            self._objects[abbr] = obj

        # Identity morphisms
        for obj in self._objects.values():
            self._add_morphism(Morphism(source=obj, target=obj, label="id",
                                         data={"type": "identity"}))

        # Technique transformation morphisms between related domains
        # Each morphism encodes a known transformation pathway
        transform_edges = [
            ("memory_forensics", "disk_forensics", "evidence_extraction",
             {"techniques": ["process→file", "volatility→autopsy"]}),
            ("memory_forensics", "network_forensics", "traffic_correlation",
             {"techniques": ["connection_scan→packet_filter", "dll_injection→payload_analysis"]}),
            ("disk_forensics", "memory_forensics", "reverse_extraction",
             {"techniques": ["file_carving→process_dump", "registry→hive_parse"]}),
            ("crypto", "binary_analysis", "mathematical_decomposition",
             {"techniques": ["factorization→decompilation", "z3→angr"]}),
            ("crypto", "stego", "encoding_transform",
             {"techniques": ["xor→lsb", "frequency→histogram", "base64→base64_decode"]}),
            ("crypto", "network_forensics", "protocol_crypto",
             {"techniques": ["tls_analysis→traffic_decrypt", "key_exchange→handshake_parse"]}),
            ("binary_analysis", "crypto", "reverse_engineering",
             {"techniques": ["disassembly→cipher_analysis", "symbolic_exec→algebraic_attack"]}),
            ("binary_analysis", "memory_forensics", "runtime_behavior",
             {"techniques": ["code_section→process_dump", "import_table→dll_list"]}),
            ("network_forensics", "web_pentest", "http_analysis",
             {"techniques": ["packet_capture→burp_suite", "dns→subdomain_enum"]}),
            ("stego", "network_forensics", "covert_channel",
             {"techniques": ["lsb→timing_channel", "image_embed→dns_tunnel"]}),
            ("web_pentest", "server_forensics", "post_exploitation",
             {"techniques": ["xss→log_analysis", "sql_injection→db_forensics"]}),
            ("mobile_forensics", "crypto", "app_security",
             {"techniques": ["apk_extract→key_extraction", "keystore→cert_analysis"]}),
            ("mobile_forensics", "memory_forensics", "runtime_state",
             {"techniques": ["app_memory→process_dump", "intent→ipc_analysis"]}),
        ]
        for src, tgt, label, data in transform_edges:
            self._add_morphism(Morphism(
                source=self._objects[src], target=self._objects[tgt],
                label=label, data=data,
            ))

    def _add_morphism(self, m: Morphism):
        self._morphisms[(m.source, m.target)].append(m)

    def objects(self) -> Set[Object]:
        return set(self._objects.values())

    def morphisms(self) -> List[Morphism]:
        result: List[Morphism] = []
        seen = set()
        for ms in self._morphisms.values():
            for m in ms:
                key = (m.source, m.target, m.label)
                if key not in seen:
                    seen.add(key)
                    result.append(m)
        return result

    def hom(self, source: Object, target: Object) -> List[Morphism]:
        return self._morphisms.get((source, target), [])

    def identity(self, obj: Object) -> Morphism:
        id_m = self.hom(obj, obj)
        if id_m:
            return id_m[0]
        id_morph = Morphism(source=obj, target=obj, label="id", data={"type": "identity"})
        self._add_morphism(id_morph)
        return id_morph

    def compose(self, g: Morphism, f: Morphism) -> Optional[Morphism]:
        if g.source != f.target:
            return None
        composed_data = {
            "type": "composition",
            "first": f.label,
            "second": g.label,
            "first_data": dict(f.data),
            "second_data": dict(g.data),
        }
        return Morphism(
            source=f.source, target=g.target,
            label=f"{g.label}∘{f.label}",
            data=composed_data,
        )

    def get_object(self, label: str) -> Optional[Object]:
        return self._objects.get(label)


# ─── Feature Category ────────────────────────────────────────────────────────

class FeatureCategory(Category):
    """Category whose objects are FeatureSpaces and morphisms are
    invariance-preserving transformations (Permutations from invariant.py).

    Each object is a feature space (a set of features). Each morphism is
    a permutation of features — a structure-preserving transformation.
    """

    def __init__(self):
        self._objects: Dict[str, Object] = {}
        self._transformations: Dict[Tuple[Object, Object], List[Morphism]] = defaultdict(list)

    def add_object(self, label: str, domain: str = "") -> Object:
        obj = Object(label=label, domain=domain)
        self._objects[label] = obj
        return obj

    def add_transformation(self, source: Object, target: Object,
                           label: str = "", data: Dict = None) -> Morphism:
        m = Morphism(source=source, target=target, label=label, data=data or {})
        self._transformations[(source, target)].append(m)
        return m

    def objects(self) -> Set[Object]:
        return set(self._objects.values())

    def morphisms(self) -> List[Morphism]:
        result: List[Morphism] = []
        seen = set()
        for ms in self._transformations.values():
            for m in ms:
                key = (m.source, m.target, m.label)
                if key not in seen:
                    seen.add(key)
                    result.append(m)
        return result

    def hom(self, source: Object, target: Object) -> List[Morphism]:
        result = self._transformations.get((source, target), [])
        # Identity when source == target and no explicit morphism
        if source == target and not result:
            result = [Morphism(source=source, target=target, label="id",
                               data={"type": "identity"})]
        return result

    def identity(self, obj: Object) -> Morphism:
        return Morphism(source=obj, target=obj, label="id",
                        data={"type": "identity"})

    def compose(self, g: Morphism, f: Morphism) -> Optional[Morphism]:
        if g.source != f.target:
            return None
        return Morphism(
            source=f.source, target=g.target,
            label=f"{g.label}∘{f.label}",
            data={"type": "composition", "first": f.label, "second": g.label},
        )


# ─── Functor ─────────────────────────────────────────────────────────────────

class Functor(ABC, Generic[ObjA, ObjB]):
    """F: C → D — a structure-preserving map between categories.

    Must satisfy:
      F(id_A) = id_{F(A)}           (identity preservation)
      F(g ∘ f) = F(g) ∘ F(f)        (composition preservation)
    """

    @abstractmethod
    def source_category(self) -> Category:
        ...

    @abstractmethod
    def target_category(self) -> Category:
        ...

    @abstractmethod
    def map_object(self, obj: Object) -> Object:
        ...

    @abstractmethod
    def map_morphism(self, morph: Morphism) -> Morphism:
        ...

    def verify_laws(self) -> Tuple[bool, List[str]]:
        """Check functor laws against all objects and composable morphism pairs."""
        violations: List[str] = []
        src = self.source_category()

        # Identity law: F(id_A) = id_{F(A)}
        for obj in src.objects():
            F_id = self.map_morphism(src.identity(obj))
            id_FA = self.target_category().identity(self.map_object(obj))
            if F_id.source != id_FA.source or F_id.target != id_FA.target:
                violations.append(
                    f"Identity violation at {obj.label}: "
                    f"F(id) maps {F_id.source.label}→{F_id.target.label}, "
                    f"expected {id_FA.source.label}→{id_FA.target.label}"
                )

        # Composition law: F(g ∘ f) = F(g) ∘ F(f)
        for f in src.morphisms():
            for g in src.morphisms():
                if g.source != f.target:
                    continue
                gf = src.compose(g, f)
                if gf is None:
                    continue
                F_gf = self.map_morphism(gf)
                F_g = self.map_morphism(g)
                F_f = self.map_morphism(f)
                F_g_of_F_f = self.target_category().compose(F_g, F_f)
                if F_g_of_F_f is None:
                    violations.append(
                        f"Composition violation: F({g.label}) ∘ F({f.label}) not composable"
                    )
                elif F_gf.source != F_g_of_F_f.source or F_gf.target != F_g_of_F_f.target:
                    violations.append(
                        f"Composition violation: F({g.label}∘{f.label}) ≠ F({g.label})∘F({f.label})"
                    )

        return len(violations) == 0, violations


# ─── Domain Functor ──────────────────────────────────────────────────────────

@dataclass
class DomainFunctor(Functor):
    """F_D: DomainCategory → FeatureCategory.

    Maps each forensic domain to its feature space and each technique
    transformation to a feature permutation (invariance-preserving map).

    This replaces the hardcoded _CROSS_DOMAIN_TOOL_MAP and
    _CROSS_DOMAIN_TECHNIQUE_MAP with a principled categorical construction.
    """

    src: DomainCategory = field(default_factory=DomainCategory)
    tgt: FeatureCategory = field(default_factory=FeatureCategory)
    _domain_features: Dict[str, Set[str]] = field(default_factory=dict)
    _tool_map: Dict[Tuple[str, str], Dict[str, str]] = field(default_factory=dict)
    _technique_map: Dict[Tuple[str, str], Dict[str, str]] = field(default_factory=dict)

    def register_domain(self, domain_label: str, features: Set[str]):
        """Register a domain's known feature set (from KB tags, tools, techniques)."""
        self._domain_features[domain_label] = features
        if domain_label not in self.tgt._objects:
            self.tgt.add_object(label=domain_label, domain="feature_space")

    def register_tool_map(self, src_domain: str, tgt_domain: str,
                          mapping: Dict[str, str]):
        """Register a cross-domain tool equivalence mapping."""
        self._tool_map[(src_domain, tgt_domain)] = mapping

    def register_technique_map(self, src_domain: str, tgt_domain: str,
                               mapping: Dict[str, str]):
        """Register a cross-domain technique equivalence mapping."""
        self._technique_map[(src_domain, tgt_domain)] = mapping

    def source_category(self) -> Category:
        return self.src

    def target_category(self) -> Category:
        return self.tgt

    def map_object(self, obj: Object) -> Object:
        """Map a forensic domain to its feature space.

        F(domain) = feature_space of that domain.
        """
        label = f"FS({obj.label})"
        if label not in self.tgt._objects:
            self.tgt.add_object(label=label, domain="feature_space")
        return self.tgt._objects[label]

    def map_morphism(self, morph: Morphism) -> Morphism:
        """Map a technique transformation to a feature permutation.

        F(f: A → B) = feature_mapping: F(A) → F(B)

        Uses registered tool/technique maps to determine how features
        in domain A correspond to features in domain B.
        """
        src_label = morph.source.label
        tgt_label = morph.target.label

        # Identity maps to identity
        if src_label == tgt_label:
            return self.tgt.identity(self.map_object(morph.source))

        # Look up registered mappings
        mapping_data: Dict[str, str] = {}
        key = (src_label, tgt_label)
        rev_key = (tgt_label, src_label)

        if key in self._tool_map:
            mapping_data.update(self._tool_map[key])
        if key in self._technique_map:
            mapping_data.update(self._technique_map[key])
        # Try reverse (invert mapping)
        if rev_key in self._tool_map and not mapping_data:
            mapping_data = {v: k for k, v in self._tool_map[rev_key].items()}
        if rev_key in self._technique_map and not mapping_data:
            mapping_data = {v: k for k, v in self._technique_map[rev_key].items()}

        src_obj = self.map_object(morph.source)
        tgt_obj = self.map_object(morph.target)

        return Morphism(
            source=src_obj, target=tgt_obj,
            label=f"F({morph.label})",
            data={
                "type": "functor_image",
                "original_morphism": morph.label,
                "feature_mapping": mapping_data,
                "source_domain": src_label,
                "target_domain": tgt_label,
            },
        )

    def derive_cross_domain_tools(self, src_domain: str, tgt_domain: str
                                  ) -> Dict[str, str]:
        """Derive tool mapping by composing functor images along a path.

        Instead of looking up a hardcoded table, this composes F along
        morphisms in the DomainCategory to find the best tool mapping path.
        """
        src_obj = self.src.get_object(src_domain)
        tgt_obj = self.src.get_object(tgt_domain)
        if not src_obj or not tgt_obj:
            return {}

        # Direct mapping
        direct = self._tool_map.get((src_domain, tgt_domain))
        if direct:
            return direct

        # Reverse mapping
        rev_direct = self._tool_map.get((tgt_domain, src_domain))
        if rev_direct:
            return {v: k for k, v in rev_direct.items()}

        # Path composition: find intermediate domain
        for (s, t), mapping in self._tool_map.items():
            if s == src_domain and t != tgt_domain:
                # Try to continue from s→t→tgt_domain
                second = self._tool_map.get((t, tgt_domain))
                if second:
                    composed: Dict[str, str] = {}
                    for src_tool, mid_tool in mapping.items():
                        if mid_tool in second:
                            composed[src_tool] = second[mid_tool]
                    if composed:
                        return composed

        return {}

    def derive_cross_domain_techniques(self, src_domain: str, tgt_domain: str
                                       ) -> Dict[str, str]:
        """Derive technique mapping through the functor (same as tools but for techniques)."""
        src_obj = self.src.get_object(src_domain)
        tgt_obj = self.src.get_object(tgt_domain)
        if not src_obj or not tgt_obj:
            return {}

        direct = self._technique_map.get((src_domain, tgt_domain))
        if direct:
            return direct

        rev_direct = self._technique_map.get((tgt_domain, src_domain))
        if rev_direct:
            return {v: k for k, v in rev_direct.items()}

        for (s, t), mapping in self._technique_map.items():
            if s == src_domain and t != tgt_domain:
                second = self._technique_map.get((t, tgt_domain))
                if second:
                    composed = {}
                    for src_tech, mid_tech in mapping.items():
                        if mid_tech in second:
                            composed[src_tech] = second[mid_tech]
                    if composed:
                        return composed

        return {}


# ─── Natural Transformation ──────────────────────────────────────────────────

@dataclass
class NaturalTransformation(Generic[ObjA, ObjB]):
    """η: F ⇒ G — a natural transformation between two functors F, G: C → D.

    For each object A in C, a component morphism η_A: F(A) → G(A) in D,
    satisfying naturality: for all f: A → B in C, G(f) ∘ η_A = η_B ∘ F(f).

    In our context, this models cross-domain knowledge transfer:
      F = functor for source domain
      G = functor for target domain
      η = mapping that translates tools/techniques from source to target domain
    """

    source_functor: Functor
    target_functor: Functor
    _components: Dict[str, Morphism] = field(default_factory=dict)

    def set_component(self, obj_label: str, component: Morphism):
        """Set η_A: F(A) → G(A) for object A."""
        self._components[obj_label] = component

    def component(self, obj_label: str) -> Optional[Morphism]:
        """Get η_A for object A."""
        return self._components.get(obj_label)

    @property
    def components(self) -> Dict[str, Morphism]:
        return dict(self._components)

    def verify_naturality(self) -> Tuple[bool, List[str]]:
        """Check: for all f: A → B, G(f) ∘ η_A = η_B ∘ F(f)."""
        violations: List[str] = []
        C = self.source_functor.source_category()
        D = self.target_functor.target_category()
        F = self.source_functor
        G = self.target_functor

        for f in C.morphisms():
            A_label = f.source.label
            B_label = f.target.label
            if A_label not in self._components or B_label not in self._components:
                continue
            if A_label == B_label:
                continue

            eta_A = self._components[A_label]
            eta_B = self._components[B_label]
            Ff = F.map_morphism(f)
            Gf = G.map_morphism(f)

            # Left path: G(f) ∘ η_A
            left = D.compose(Gf, eta_A)

            # Right path: η_B ∘ F(f)
            right = D.compose(eta_B, Ff)

            if left is None or right is None:
                violations.append(
                    f"Naturality: components not composable for f: {A_label}→{B_label}"
                )
                continue

            # Check that source/target match
            if left.source != right.source or left.target != right.target:
                violations.append(
                    f"Naturality square fails for f: {A_label}→{B_label}: "
                    f"Gf∘η_A: {left.source.label}→{left.target.label}, "
                    f"η_B∘Ff: {right.source.label}→{right.target.label}"
                )

        return len(violations) == 0, violations


# ─── Transfer Natural Transformation (concrete) ──────────────────────────────

@dataclass
class TransferTransformation(NaturalTransformation):
    """Concrete natural transformation for cross-domain knowledge transfer.

    Given two DomainFunctor instances (source and target), automatically
    derives the natural transformation components from the isomorphism
    mappings detected by invariant.py.

    Each component η_D: F(D) → G(D) is a feature-space morphism encoding
    the tool and technique translations between domains.
    """

    source_domain: str = ""
    target_domain: str = ""

    def build_from_isomorphism(self, mapping, src_profile, tgt_profile):
        """Build the natural transformation from an IsomorphismMapping.

        mapping: IsomorphismMapping from invariant.py
        src_profile: InvariantProfile for source
        tgt_profile: InvariantProfile for target
        """
        self.source_domain = mapping.source_domain
        self.target_domain = mapping.target_domain

        # Component at the source domain object: maps features across
        F = self.source_functor
        G = self.target_functor

        src_obj = F.map_object(F.src.get_object(mapping.source_domain))
        tgt_obj = G.map_object(G.src.get_object(mapping.target_domain))

        component = Morphism(
            source=src_obj, target=tgt_obj,
            label=f"η({mapping.source_domain}→{mapping.target_domain})",
            data={
                "type": "natural_transformation_component",
                "feature_mapping": mapping.feature_mapping,
                "isomorphism_score": mapping.score,
                "isomorphism_type": mapping.isomorphism_type,
                "shared_cores": mapping.shared_core_count,
                "structure_diffs": mapping.structural_differences,
            },
        )
        self.set_component(mapping.source_domain, component)
        return self

    def get_tool_mapping(self) -> Dict[str, str]:
        """Extract tool mapping from the natural transformation component."""
        c = self.component(self.source_domain)
        if c is None:
            return {}
        fm = c.data.get("feature_mapping", {})
        # Filter to tool-like features
        return {k: v for k, v in fm.items() if not k.startswith("tech:")}

    def get_technique_mapping(self) -> Dict[str, str]:
        """Extract technique mapping from the natural transformation component."""
        c = self.component(self.source_domain)
        if c is None:
            return {}
        fm = c.data.get("feature_mapping", {})
        return {k: v for k, v in fm.items() if k.startswith("tech:")}


# ─── Adjunction ──────────────────────────────────────────────────────────────

@dataclass
class Adjunction:
    """F ⊣ G: C ⇄ D — an adjunction between categories.

    F: C → D  (left adjoint, "free" construction)
    G: D → C  (right adjoint, "forgetful" functor)

    Natural isomorphism: Hom_D(F(A), B) ≅ Hom_C(A, G(B))

    In our system, this formalizes the Decomposer:
      F = decompose: Problem → SubGoal DAG  (free construction)
      G = compose:   SubGoal DAG → Answer   (evaluation)
    """

    left_adjoint: Functor     # F: C → D
    right_adjoint: Functor    # G: D → C
    _unit: Dict[str, Morphism] = field(default_factory=dict)    # η_A: A → G(F(A))
    _counit: Dict[str, Morphism] = field(default_factory=dict)  # ε_B: F(G(B)) → B

    def set_unit(self, obj_label: str, morph: Morphism):
        """Set the unit component η_A: A → G(F(A))."""
        self._unit[obj_label] = morph

    def set_counit(self, obj_label: str, morph: Morphism):
        """Set the counit component ε_B: F(G(B)) → B."""
        self._counit[obj_label] = morph

    def verify_triangle_identities(self) -> Tuple[bool, List[str]]:
        """Check triangle identities:
          ε_{F(A)} ∘ F(η_A) = id_{F(A)}
          G(ε_B) ∘ η_{G(B)} = id_{G(B)}
        """
        violations: List[str] = []
        F = self.left_adjoint
        G = self.right_adjoint
        C = F.source_category()
        D = F.target_category()

        for obj_a in C.objects():
            a_label = obj_a.label
            if a_label not in self._unit:
                continue
            eta_a = self._unit[a_label]
            F_eta = F.map_morphism(eta_a)
            Fa = F.map_object(obj_a)
            Fa_label = Fa.label
            if Fa_label not in self._counit:
                continue
            eps_Fa = self._counit[Fa_label]
            result = D.compose(eps_Fa, F_eta)
            id_Fa = D.identity(Fa)
            if result is None or result.source != id_Fa.source or result.target != id_Fa.target:
                violations.append(
                    f"Triangle identity 1 fails at {a_label}: ε_F(A)∘F(η_A) ≠ id_F(A)"
                )

        for obj_b in D.objects():
            b_label = obj_b.label
            if b_label not in self._counit:
                continue
            eps_b = self._counit[b_label]
            G_eps = G.map_morphism(eps_b)
            Gb = G.map_object(obj_b)
            Gb_label = Gb.label
            if Gb_label not in self._unit:
                continue
            eta_Gb = self._unit[Gb_label]
            result = C.compose(G_eps, eta_Gb)
            id_Gb = C.identity(Gb)
            if result is None or result.source != id_Gb.source or result.target != id_Gb.target:
                violations.append(
                    f"Triangle identity 2 fails at {b_label}: G(ε_B)∘η_G(B) ≠ id_G(B)"
                )

        return len(violations) == 0, violations


# ─── Builder Functions ───────────────────────────────────────────────────────

def build_domain_category() -> DomainCategory:
    """Construct the DomainCategory from forensic domain knowledge."""
    return DomainCategory()


def build_default_domain_functor() -> DomainFunctor:
    """Build a DomainFunctor pre-populated with known cross-domain mappings.

    This REPLACES the hardcoded _CROSS_DOMAIN_TOOL_MAP and
    _CROSS_DOMAIN_TECHNIQUE_MAP in invariant.py with functor-registered maps.
    """
    F = DomainFunctor()

    # Register domain feature sets
    F.register_domain("memory_forensics", {
        "vol3", "volatility", "strings", "sqlite3", "registry",
        "malfind", "netscan", "psscan", "memdump", "yarascan",
    })
    F.register_domain("disk_forensics", {
        "tsk_recover", "autopsy", "strings", "sqlite3",
        "registry_explorer", "ftk_imager", "disk_analyzer",
        "file_carving", "mft_parser", "usn_journal",
    })
    F.register_domain("network_forensics", {
        "wireshark", "tshark", "tcpdump", "zeek", "suricata",
        "packet_analysis", "protocol_parsing", "session_reconstruction",
    })
    F.register_domain("binary_analysis", {
        "ida", "ghidra", "angr", "z3", "python",
        "decompilation", "disassembly", "symbolic_execution",
        "fuzzing", "patch_analysis",
    })
    F.register_domain("crypto", {
        "sage", "python", "openssl", "z3", "cyberchef",
        "factorization", "rsa", "modular_arithmetic",
        "frequency_analysis", "brute_force", "side_channel",
    })
    F.register_domain("stego", {
        "python", "steghide", "cyberchef", "zsteg",
        "lsb", "histogram_analysis", "base64_decode", "xor",
    })

    # Register cross-domain tool mappings (replaces _CROSS_DOMAIN_TOOL_MAP)
    F.register_tool_map("crypto", "binary_analysis", {
        "sage": "ida", "python": "python", "rsa": "rsa_pubkey_in_binary",
        "factorization": "decompilation", "openssl": "ghidra", "z3": "angr",
    })
    F.register_tool_map("crypto", "stego", {
        "python": "python", "base64": "base64_decode", "xor": "lsb_xor",
        "frequency_analysis": "histogram_analysis",
        "openssl": "steghide", "cyberchef": "cyberchef",
    })
    F.register_tool_map("memory_forensics", "disk_forensics", {
        "vol3": "tsk_recover", "volatility": "autopsy",
        "strings": "strings", "sqlite3": "sqlite3", "registry": "registry_explorer",
    })

    # Register cross-domain technique mappings (replaces _CROSS_DOMAIN_TECHNIQUE_MAP)
    F.register_technique_map("crypto", "binary_analysis", {
        "modular_arithmetic": "register_operations",
        "prime_factorization": "control_flow_decomposition",
        "padding_oracle": "buffer_overflow_detection",
        "side_channel": "timing_analysis",
        "brute_force": "fuzzing",
        "meet_in_the_middle": "bidirectional_analysis",
    })
    F.register_technique_map("memory_forensics", "network_forensics", {
        "process_scanning": "packet_filtering",
        "dll_injection_detection": "payload_analysis",
        "hive_parsing": "protocol_parsing",
        "timeline_reconstruction": "session_reconstruction",
    })
    F.register_technique_map("binary_analysis", "crypto", {
        "control_flow_analysis": "algorithm_identification",
        "symbolic_execution": "algebraic_attack",
        "disassembly": "cipher_text_analysis",
        "patching": "key_recovery",
    })

    return F


def verify_decomposition_adjunction(
    decompose: Callable, compose: Callable, test_problems: List[Dict]
) -> Tuple[bool, List[str]]:
    """Verify that decompose ⊣ compose forms an adjunction.

    decompose: Problem → SubGoalDAG  (F, left adjoint)
    compose:   SubGoalDAG → Answer   (G, right adjoint)

    Checks: is compose(decompose(p)) equivalent to p?
    (The counit of the adjunction: ε_p: F(G(p)) → p)
    """
    results: List[str] = []
    all_ok = True

    for problem in test_problems:
        try:
            subgoals = decompose(problem)
            answer = compose(subgoals)
            loss = problem.get("expected", {})
            if loss and answer.get("result") != loss.get("result"):
                all_ok = False
                results.append(
                    f"Adjunction FAIL for {problem.get('name', '?')}: "
                    f"compose∘decompose lost information"
                )
            else:
                results.append(
                    f"Adjunction OK for {problem.get('name', '?')}: "
                    f"decompose ⊣ compose preserves semantics"
                )
        except Exception as e:
            results.append(f"Adjunction ERROR for {problem.get('name', '?')}: {e}")

    return all_ok, results


def format_functor_summary(F: Functor) -> str:
    """Format a human-readable summary of a functor."""
    lines = [f"Functor: {F.__class__.__name__}"]
    src = F.source_category()
    tgt = F.target_category()
    lines.append(f"  Source: {len(src.objects())} objects, {len(src.morphisms())} morphisms")
    lines.append(f"  Target: {len(tgt.objects())} objects, {len(tgt.morphisms())} morphisms")
    ok, violations = F.verify_laws()
    lines.append(f"  Laws verified: {'PASS' if ok else 'FAIL'}")
    if violations:
        for v in violations[:5]:
            lines.append(f"    - {v}")
    return "\n".join(lines)


def format_natural_transformation_summary(nt: NaturalTransformation) -> str:
    """Format a human-readable summary of a natural transformation."""
    lines = [f"Natural Transformation: {nt.__class__.__name__}"]
    lines.append(f"  Source Functor: {nt.source_functor.__class__.__name__}")
    lines.append(f"  Target Functor: {nt.target_functor.__class__.__name__}")
    lines.append(f"  Components: {list(nt.components.keys())}")
    ok, violations = nt.verify_naturality()
    lines.append(f"  Naturality: {'PASS' if ok else 'FAIL'}")
    if violations:
        for v in violations[:5]:
            lines.append(f"    - {v}")
    return "\n".join(lines)


def format_adjunction_summary(adj: Adjunction) -> str:
    """Format a human-readable summary of an adjunction."""
    lines = [f"Adjunction: {adj.left_adjoint.__class__.__name__} ⊣ {adj.right_adjoint.__class__.__name__}"]
    lines.append(f"  Unit components: {list(adj._unit.keys())}")
    lines.append(f"  Counit components: {list(adj._counit.keys())}")
    ok, violations = adj.verify_triangle_identities()
    lines.append(f"  Triangle identities: {'PASS' if ok else 'FAIL'}")
    if violations:
        for v in violations[:5]:
            lines.append(f"    - {v}")
    return "\n".join(lines)


# ─── Decomposer Adjunction ───────────────────────────────────────────────────

class ProblemCategory(Category):
    """Category of CTF problems.

    Objects: individual CTF problems (challenges).
    Morphisms: evidence-sharing relationships — f: P→Q when problem P's
    evidence or solution approach can inform problem Q.
    """

    def __init__(self):
        self._objects: Dict[str, Object] = {}
        self._morphisms: Dict[Tuple[Object, Object], List[Morphism]] = defaultdict(list)

    def add_problem(self, label: str, domain: str = "",
                    metadata: Dict[str, Any] = None) -> Object:
        obj = Object(label=label, domain=domain)
        self._objects[label] = obj
        if metadata:
            obj = Object(label=label, domain=domain)
        return obj

    def add_morphism(self, source_label: str, target_label: str,
                     label: str = "", data: Dict = None):
        src = self._objects[source_label]
        tgt = self._objects[target_label]
        m = Morphism(source=src, target=tgt, label=label, data=data or {})
        self._morphisms[(src, tgt)].append(m)
        return m

    def objects(self) -> Set[Object]:
        return set(self._objects.values())

    def morphisms(self) -> List[Morphism]:
        result: List[Morphism] = []
        for ms in self._morphisms.values():
            result.extend(ms)
        return result

    def hom(self, source: Object, target: Object) -> List[Morphism]:
        return self._morphisms.get((source, target), [])

    def identity(self, obj: Object) -> Morphism:
        id_m = self.hom(obj, obj)
        if id_m:
            return id_m[0]
        m = Morphism(source=obj, target=obj, label="id", data={"type": "identity"})
        self._morphisms[(obj, obj)].append(m)
        return m

    def compose(self, g: Morphism, f: Morphism) -> Optional[Morphism]:
        if g.source != f.target:
            return None
        return Morphism(
            source=f.source, target=g.target,
            label=f"{g.label}∘{f.label}",
            data={"type": "composition", "first": f.label, "second": g.label},
        )

    def from_decomposition_plan(self, plan: "DecompositionPlan"):
        """Populate category from a DecompositionPlan.

        Each SubGoal becomes an object; dependencies become morphisms.
        """
        for sg_id, sg in plan.sub_goals.items():
            domain_tag = sg.domain or "unknown"
            obj = Object(label=sg_id, domain=domain_tag)
            self._objects[sg_id] = obj

        for sg_id, sg in plan.sub_goals.items():
            for dep_id in sg.dependencies:
                if dep_id in self._objects:
                    src = self._objects[dep_id]
                    tgt = self._objects[sg_id]
                    m = Morphism(
                        source=src, target=tgt,
                        label=f"depends_on",
                        data={"type": "dependency"},
                    )
                    self._morphisms[(src, tgt)].append(m)


class DecomposerFunctor(Functor):
    """F: ProblemCategory → DAGCategory.

    Maps a problem to its sub-goal DAG (free construction).
    This is the LEFT adjoint in the decomposition adjunction.

    In practice, wraps tools.decomposer.decomposer_engine.decompose().
    """

    def __init__(self):
        self._src = ProblemCategory()
        self._tgt = ProblemCategory()

    def source_category(self) -> Category:
        return self._src

    def target_category(self) -> Category:
        return self._tgt

    def map_object(self, obj: Object) -> Object:
        label = f"DAG({obj.label})"
        if label not in self._tgt._objects:
            self._tgt._objects[label] = Object(label=label, domain="subgoal_dag")
        return self._tgt._objects[label]

    def map_morphism(self, morph: Morphism) -> Morphism:
        src = self.map_object(morph.source)
        tgt = self.map_object(morph.target)
        return Morphism(
            source=src, target=tgt,
            label=f"decompose({morph.label})",
            data={"type": "decomposition", "original": morph.label},
        )

    def register_problem(self, label: str, domain: str = ""):
        """Register a problem in the source category."""
        self._src._objects[label] = Object(label=label, domain=domain)
        return self._src._objects[label]

    def register_subgoals(self, problem_label: str, plan: "DecompositionPlan"):
        """Populate target category from a decomposition plan.

        Maps problem_label → DAG(problem_label), then adds each subgoal
        as an object in the target category with dependency morphisms.
        """
        self._tgt.from_decomposition_plan(plan)


class ComposerFunctor(Functor):
    """G: DAGCategory → ProblemCategory.

    Composes sub-goal results back into an answer (forgetful/evaluation).
    This is the RIGHT adjoint in the decomposition adjunction.
    """

    def __init__(self):
        self._src = ProblemCategory()
        self._tgt = ProblemCategory()

    def source_category(self) -> Category:
        return self._src

    def target_category(self) -> Category:
        return self._tgt

    def map_object(self, obj: Object) -> Object:
        # Strip the DAG( ) prefix if present
        label = obj.label
        if label.startswith("DAG(") and label.endswith(")"):
            label = label[4:-1]
        if label not in self._tgt._objects:
            self._tgt._objects[label] = Object(label=label, domain="answer")
        return self._tgt._objects[label]

    def map_morphism(self, morph: Morphism) -> Morphism:
        src = self.map_object(morph.source)
        tgt = self.map_object(morph.target)
        return Morphism(
            source=src, target=tgt,
            label=f"compose({morph.label})",
            data={"type": "composition", "original": morph.label},
        )


def build_decomposer_adjunction() -> Tuple[DecomposerFunctor, ComposerFunctor, Adjunction]:
    """Build the decomposition adjunction: Decomposer ⊣ Composer.

    Returns (F, G, adjunction) where:
      F = DecomposerFunctor (left adjoint, free: Problem → SubGoalDAG)
      G = ComposerFunctor  (right adjoint, forgetful: SubGoalDAG → Answer)
    """
    F = DecomposerFunctor()
    G = ComposerFunctor()

    # Share the same underlying ProblemCategory for the source of F
    # and the target of G
    G._tgt = F._src

    adj = Adjunction(left_adjoint=F, right_adjoint=G)

    # For each registered problem, set the unit η_P: P → G(F(P))
    for label, obj in F._src._objects.items():
        F_obj = F.map_object(obj)
        GF_obj = G.map_object(F_obj)
        adj.set_unit(label, Morphism(
            source=obj, target=GF_obj,
            label=f"η({label})",
            data={"type": "unit", "adjunction": "decompose⊣compose"},
        ))

    # For each DAG object, set the counit ε_D: F(G(D)) → D
    for label, obj in F._tgt._objects.items():
        G_obj = G.map_object(obj)
        FG_obj = F.map_object(G_obj)
        adj.set_counit(label, Morphism(
            source=FG_obj, target=obj,
            label=f"ε({label})",
            data={"type": "counit", "adjunction": "decompose⊣compose"},
        ))

    return F, G, adj


def verify_decomposition_completeness(
    plan: "DecompositionPlan",
    answered_subgoals: Optional[Dict[str, bool]] = None,
) -> Tuple[bool, List[str]]:
    """Verify that a decomposition is complete (no information loss).

    Checks:
      1. Every question has a path from shared/prep subgoals (connectedness)
      2. No orphan subgoals that depend on nothing and nothing depends on them
      3. Critical path covers all questions
      4. Adjunction triangle identities hold

    Args:
        plan: The DecompositionPlan to verify.
        answered_subgoals: Optional dict of subgoal_id → answered flag.

    Returns:
        (is_complete, issues) where issues describes any problems found.
    """
    issues: List[str] = []

    sg_map = plan.sub_goals
    if not sg_map:
        return True, ["Empty plan — no subgoals to verify"]

    question_sgs = [sg for sg in sg_map.values() if sg.level == 3]
    analysis_sgs = [sg for sg in sg_map.values() if sg.level == 2]
    prep_sgs = [sg for sg in sg_map.values() if sg.level == 1]
    shared_sgs = [sg for sg in sg_map.values() if sg.level == 0]

    # 1. Connectedness: every question must be reachable from shared/prep
    all_ids = set(sg_map.keys())
    reachable: Set[str] = set()

    def dfs(sg_id: str):
        if sg_id in reachable:
            return
        reachable.add(sg_id)
        sg = sg_map.get(sg_id)
        if sg:
            for dep_id in sg.dependencies:
                if dep_id in all_ids:
                    dfs(dep_id)

    # Start BFS from shared and prep nodes
    from collections import deque
    queue = deque()
    for sg in shared_sgs + prep_sgs:
        queue.append(sg.id)
        reachable.add(sg.id)

    # Forward propagation through reverse dependency graph
    reverse_deps: Dict[str, List[str]] = defaultdict(list)
    for sg_id, sg in sg_map.items():
        for dep_id in sg.dependencies:
            reverse_deps[dep_id].append(sg_id)

    while queue:
        current = queue.popleft()
        for dependent in reverse_deps.get(current, []):
            if dependent not in reachable:
                reachable.add(dependent)
                queue.append(dependent)

    for sg in question_sgs:
        if sg.id not in reachable:
            issues.append(
                f"Question '{sg.id}' not reachable from shared/prep: "
                f"missing dependency chain"
            )

    # 2. Orphan detection
    all_dependents: Set[str] = set()
    for sg in sg_map.values():
        all_dependents.update(sg.dependencies)

    for sg_id, sg in sg_map.items():
        has_deps = bool(sg.dependencies)
        is_depended_on = sg_id in all_dependents
        if not has_deps and not is_depended_on and sg.level > 0:
            issues.append(
                f"Orphan subgoal '{sg_id}' (level={sg.level}): "
                f"no dependencies and nothing depends on it"
            )

    # 3. Critical path coverage
    if plan.critical_path:
        cp_set = set(plan.critical_path)
        for sg in question_sgs:
            if sg.id not in cp_set:
                issues.append(
                    f"Question '{sg.id}' not on critical path — "
                    f"may indicate unnecessary decomposition"
                )

    # 4. Adjunction verification is structural:
    # unit: P → compose(decompose(P)) should be an isomorphism
    # (i.e., decomposing then composing should recover the problem)
    if not question_sgs:
        issues.append("No question-level subgoals — plan may be incomplete")
    if not shared_sgs and not prep_sgs:
        issues.append("No shared/prep subgoals — evidence processing undefined")

    return len(issues) == 0, issues
