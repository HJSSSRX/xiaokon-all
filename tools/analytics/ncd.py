"""Normalized Compression Distance — 归一化压缩距离.

NCD is a universal similarity metric based on Kolmogorov complexity, approximated
by real-world compressors (zlib, bzip2, lzma). It is parameter-free, feature-agnostic,
and satisfies the metric axioms up to the compressor's deviation from ideality.

  NCD(x, y) = (C(xy) - min(C(x), C(y))) / max(C(x), C(y))

  where C = compressed size in bytes.

Properties:
  - NCD ≈ 0: objects are very similar (compress well together)
  - NCD ≈ 1: objects are dissimilar (no shared structure)
  - NCD is symmetric, non-negative, and satisfies the triangle inequality

Applications:
  - Problem similarity without manual feature engineering
  - Cross-validation of group-theoretic invariant profiles
  - Anomaly/novelty detection (high NCD from all known problems)
  - Hierarchical clustering of the knowledge base
"""

import zlib
import bz2
import lzma
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Set, Tuple, Optional, Callable, Any
import math


# ─── Compressor interface ──────────────────────────────────────────────────────

def _zlib_compress(data: bytes) -> int:
    return len(zlib.compress(data, level=9))


def _bz2_compress(data: bytes) -> int:
    return len(bz2.compress(data, compresslevel=9))


def _lzma_compress(data: bytes) -> int:
    return len(lzma.compress(data))


COMPRESSORS: Dict[str, Callable[[bytes], int]] = {
    "zlib": _zlib_compress,
    "bz2": _bz2_compress,
    "lzma": _lzma_compress,
}


# ─── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class NCDMatrix:
    """Pairwise NCD distances between objects.

    Stores a lower-triangular matrix indexed by object IDs.
    """
    object_ids: List[str] = field(default_factory=list)
    distances: Dict[Tuple[int, int], float] = field(default_factory=dict)
    compressor: str = "zlib"
    n_objects: int = 0

    def __post_init__(self):
        self.n_objects = len(self.object_ids)

    def get(self, id_a: str, id_b: str) -> Optional[float]:
        """Get NCD between two objects by ID."""
        if id_a == id_b:
            return 0.0
        i = self.object_ids.index(id_a) if id_a in self.object_ids else -1
        j = self.object_ids.index(id_b) if id_b in self.object_ids else -1
        if i < 0 or j < 0:
            return None
        if i > j:
            i, j = j, i
        return self.distances.get((i, j))

    def get_by_idx(self, i: int, j: int) -> float:
        if i == j:
            return 0.0
        if i > j:
            i, j = j, i
        return self.distances.get((i, j), 1.0)

    def nearest_neighbors(self, obj_id: str, k: int = 5) -> List[Tuple[str, float]]:
        """Top-k nearest neighbors by NCD."""
        i = self.object_ids.index(obj_id) if obj_id in self.object_ids else -1
        if i < 0:
            return []
        nn = []
        for j in range(self.n_objects):
            if j == i:
                continue
            d = self.get_by_idx(i, j)
            nn.append((self.object_ids[j], d))
        nn.sort(key=lambda x: x[1])
        return nn[:k]

    def avg_distance(self) -> float:
        if not self.distances:
            return 0.0
        return sum(self.distances.values()) / len(self.distances)

    def max_distance(self) -> float:
        if not self.distances:
            return 0.0
        return max(self.distances.values())

    def min_distance(self) -> float:
        if not self.distances:
            return 0.0
        return min(self.distances.values())

    def to_similarity(self, obj_id: str) -> Dict[str, float]:
        """Convert NCD to similarity: sim = 1 - NCD (clamped to [0, 1])."""
        i = self.object_ids.index(obj_id) if obj_id in self.object_ids else -1
        if i < 0:
            return {}
        return {
            self.object_ids[j]: max(0.0, min(1.0, 1.0 - self.get_by_idx(i, j)))
            for j in range(self.n_objects) if j != i
        }


@dataclass
class NCDCluster:
    """A node in the NCD-based hierarchical clustering dendrogram."""
    label: str = ""
    children: List["NCDCluster"] = field(default_factory=list)
    distance: float = 0.0  # merge distance
    size: int = 1
    is_leaf: bool = True


# ─── NCD Computation ──────────────────────────────────────────────────────────

def compute_ncd(
    x: bytes, y: bytes, compressor: str = "zlib"
) -> float:
    """Compute NCD(x, y) for two byte strings.

    Args:
        x: First object as bytes.
        y: Second object as bytes.
        compressor: One of 'zlib', 'bz2', 'lzma'.

    Returns:
        NCD value (typically in [0.0, 1.1+]). Values > 1.1 are clamped to 1.0.
    """
    compress = COMPRESSORS.get(compressor, _zlib_compress)
    cx = compress(x)
    cy = compress(y)
    cxy = compress(x + y)
    if max(cx, cy) == 0:
        return 0.0
    ncd = (cxy - min(cx, cy)) / max(cx, cy)
    return min(1.0, max(0.0, ncd))


def compute_ncd_text(
    text_a: str, text_b: str, compressor: str = "zlib"
) -> float:
    """Compute NCD for two text strings (UTF-8 encoded)."""
    return compute_ncd(text_a.encode("utf-8"), text_b.encode("utf-8"), compressor)


def ncd_matrix(
    objects: Dict[str, bytes], compressor: str = "zlib"
) -> NCDMatrix:
    """Compute pairwise NCD matrix for a collection of objects.

    Args:
        objects: Dict mapping object ID to its byte representation.
        compressor: Compressor to use.

    Returns:
        NCDMatrix with all pairwise distances.
    """
    obj_ids = list(objects.keys())
    matrix = NCDMatrix(object_ids=obj_ids, compressor=compressor)

    # Pre-compute compressed sizes for all individual objects
    compress = COMPRESSORS.get(compressor, _zlib_compress)
    compressed_sizes = {oid: compress(data) for oid, data in objects.items()}

    # Compute pairwise NCD
    for a_idx in range(len(obj_ids)):
        for b_idx in range(a_idx + 1, len(obj_ids)):
            id_a = obj_ids[a_idx]
            id_b = obj_ids[b_idx]
            data_a = objects[id_a]
            data_b = objects[id_b]
            cxy = compress(data_a + data_b)
            cx = compressed_sizes[id_a]
            cy = compressed_sizes[id_b]
            if max(cx, cy) == 0:
                ncd = 0.0
            else:
                ncd = (cxy - min(cx, cy)) / max(cx, cy)
                ncd = min(1.0, max(0.0, ncd))
            matrix.distances[(a_idx, b_idx)] = ncd

    return matrix


def ncd_matrix_from_features(
    problem_features: Dict[str, List[str]],
    compressor: str = "zlib",
    sort_features: bool = True,
) -> NCDMatrix:
    """Compute NCD matrix from problem feature lists.

    Each problem is represented as a space-separated string of its features.
    """
    objects: Dict[str, bytes] = {}
    for pid, features in problem_features.items():
        feats = sorted(features) if sort_features else list(features)
        text = " ".join(feats)
        objects[pid] = text.encode("utf-8")
    return ncd_matrix(objects, compressor)


def ncd_matrix_from_files(
    file_paths: Dict[str, str],
    compressor: str = "zlib",
) -> NCDMatrix:
    """Compute NCD matrix from file contents (full text)."""
    objects: Dict[str, bytes] = {}
    for pid, path in file_paths.items():
        try:
            with open(path, "rb") as f:
                objects[pid] = f.read()
        except (OSError, IOError):
            continue
    return ncd_matrix(objects, compressor)


# ─── Clustering ────────────────────────────────────────────────────────────────

def ncd_hierarchical_clustering(
    matrix: NCDMatrix,
    min_clusters: int = 1,
) -> NCDCluster:
    """Agglomerative hierarchical clustering from NCD matrix (UPGMA / average linkage).

    Builds a dendrogram by repeatedly merging the closest pair of clusters.

    Returns:
        Root NCDCluster node (dendrogram).
    """
    n = matrix.n_objects
    # Initialize: each object is its own cluster
    clusters: List[NCDCluster] = [
        NCDCluster(label=oid, size=1, is_leaf=True)
        for oid in matrix.object_ids
    ]
    active = set(range(n))

    # Distance between clusters (UPGMA: average linkage)
    cluster_dist: Dict[Tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            cluster_dist[(i, j)] = matrix.get_by_idx(i, j)

    while len(active) > max(1, min_clusters):
        # Find closest pair
        best_pair = None
        best_dist = float("inf")
        for (a, b), d in cluster_dist.items():
            if a in active and b in active and d < best_dist:
                best_dist = d
                best_pair = (a, b)

        if best_pair is None:
            break

        a, b = best_pair
        active.discard(a)
        active.discard(b)

        # Merge a and b
        new_idx = len(clusters)
        new_cluster = NCDCluster(
            label=f"cluster_{new_idx}",
            children=[clusters[a], clusters[b]],
            distance=best_dist,
            size=clusters[a].size + clusters[b].size,
            is_leaf=False,
        )
        clusters.append(new_cluster)
        active.add(new_idx)

        # Update distances to other active clusters (UPGMA weighted average)
        for c in list(active):
            if c == new_idx:
                continue
            d_ac = _get_cluster_dist(a, c, cluster_dist, len(clusters))
            d_bc = _get_cluster_dist(b, c, cluster_dist, len(clusters))
            size_a = clusters[a].size
            size_b = clusters[b].size
            new_dist = (size_a * d_ac + size_b * d_bc) / (size_a + size_b)
            key = (c, new_idx) if c < new_idx else (new_idx, c)
            cluster_dist[key] = new_dist

        # Remove old keys
        to_remove = []
        for (x, y) in list(cluster_dist.keys()):
            if x in (a, b) or y in (a, b):
                to_remove.append((x, y))
        for key in to_remove:
            del cluster_dist[key]

    # Return root (last remaining active cluster)
    remaining = list(active)
    if len(remaining) == 1:
        return clusters[remaining[0]]
    # Multiple remain: create artificial root
    root = NCDCluster(label="root", is_leaf=False, size=n)
    for idx in remaining:
        root.children.append(clusters[idx])
        root.distance = max(root.distance, clusters[idx].distance)
    return root


def _get_cluster_dist(
    a: int, b: int, cluster_dist: Dict[Tuple[int, int], float], _n: int
) -> float:
    key = (a, b) if a < b else (b, a)
    return cluster_dist.get(key, 1.0)


def flatten_clusters(
    root: NCDCluster, threshold: float = 0.5
) -> List[NCDCluster]:
    """Flatten dendrogram by cutting at a distance threshold.

    Returns clusters whose merge distance is below the threshold.
    """
    if root.is_leaf:
        return [root]
    if root.distance < threshold:
        return [root]
    result = []
    for child in root.children:
        result.extend(flatten_clusters(child, threshold))
    return result


def get_cluster_leaves(root: NCDCluster) -> List[str]:
    """Get all leaf labels in a cluster subtree."""
    if root.is_leaf:
        return [root.label]
    leaves = []
    for child in root.children:
        leaves.extend(get_cluster_leaves(child))
    return leaves


# ─── Cross-Validation with Invariants ──────────────────────────────────────────

def compare_ncd_with_invariants(
    ncd_matrix: NCDMatrix,
    profiles: List[Any],  # List[InvariantProfile]
) -> Dict[str, Any]:
    """Cross-validate NCD similarity against group-theoretic invariant overlap.

    Computes the correlation between:
      - NCD-based similarity: sim_ncd(i,j) = 1 - NCD(i,j)
      - Invariant-based similarity: Jaccard of core invariant feature sets

    High correlation means both methods agree on problem structure.
    Low correlation flags problems where NCD discovers relationships
    invisible to feature-based methods.
    """
    profile_map = {p.problem_id: p for p in profiles}
    common_ids = [
        oid for oid in ncd_matrix.object_ids if oid in profile_map
    ]

    if len(common_ids) < 3:
        return {"error": "Not enough overlapping objects"}

    ncd_sims = []
    inv_sims = []
    disagreements = []

    for i in range(len(common_ids)):
        for j in range(i + 1, len(common_ids)):
            id_a = common_ids[i]
            id_b = common_ids[j]

            # NCD similarity
            ncd_dist = ncd_matrix.get(id_a, id_b)
            if ncd_dist is None:
                continue
            ncd_sim = 1.0 - ncd_dist

            # Invariant similarity (Jaccard on core invariant features)
            pa = profile_map[id_a]
            pb = profile_map[id_b]
            feats_a = set().union(
                *[set(itemset) for itemset in pa.core_invariants]
            ) if pa.core_invariants else set()
            feats_b = set().union(
                *[set(itemset) for itemset in pb.core_invariants]
            ) if pb.core_invariants else set()
            union = len(feats_a | feats_b)
            intersection = len(feats_a & feats_b)
            inv_sim = intersection / union if union > 0 else 0.0

            ncd_sims.append(ncd_sim)
            inv_sims.append(inv_sim)

            # Flag disagreements: high NCD similarity but low invariant similarity
            if ncd_sim > 0.5 and inv_sim < 0.2:
                disagreements.append({
                    "a": id_a, "b": id_b,
                    "ncd_similarity": round(ncd_sim, 4),
                    "invariant_similarity": round(inv_sim, 4),
                    "interpretation": "NCD发现隐藏相似性 — 可能共享非特征化结构",
                })
            elif inv_sim > 0.5 and ncd_sim < 0.2:
                disagreements.append({
                    "a": id_a, "b": id_b,
                    "ncd_similarity": round(ncd_sim, 4),
                    "invariant_similarity": round(inv_sim, 4),
                    "interpretation": "不变量高度一致但NCD不相似 — 特征粒度可能过粗",
                })

    # Pearson correlation
    corr = _pearson_correlation(ncd_sims, inv_sims)

    return {
        "n_compared": len(ncd_sims),
        "pearson_correlation": round(corr, 4) if corr is not None else None,
        "avg_ncd_similarity": round(sum(ncd_sims) / len(ncd_sims), 4) if ncd_sims else 0,
        "avg_invariant_similarity": round(sum(inv_sims) / len(inv_sims), 4) if inv_sims else 0,
        "disagreements": disagreements[:10],
        "interpretation": (
            "高度正相关 → NCD与不变量分析一致"
            if corr and corr > 0.6 else
            "低/负相关 → NCD发现了特征分析遗漏的结构信息"
            if corr is not None else
            "无法计算"
        ),
    }


def _pearson_correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


def detect_ncd_anomalies(
    matrix: NCDMatrix, z_threshold: float = 2.0
) -> List[Dict[str, Any]]:
    """Detect anomalous objects whose avg NCD from others is unusually high.

    Objects with mean NCD > mean(all) + z_threshold * std(all) are flagged.
    These may represent unique/novel problem types with no close relatives.
    """
    if matrix.n_objects < 3:
        return []

    # Per-object mean NCD to all others
    means = []
    for i in range(matrix.n_objects):
        dists = [
            matrix.get_by_idx(i, j)
            for j in range(matrix.n_objects) if j != i
        ]
        means.append(sum(dists) / len(dists))

    global_mean = sum(means) / len(means)
    global_std = math.sqrt(
        sum((m - global_mean) ** 2 for m in means) / len(means)
    )

    if global_std == 0:
        return []

    anomalies = []
    threshold = global_mean + z_threshold * global_std
    for i, m in enumerate(means):
        if m > threshold:
            anomalies.append({
                "object_id": matrix.object_ids[i],
                "mean_ncd": round(m, 4),
                "global_mean": round(global_mean, 4),
                "z_score": round((m - global_mean) / global_std, 2),
            })

    anomalies.sort(key=lambda x: -x["z_score"])
    return anomalies


# ─── Formatters ────────────────────────────────────────────────────────────────


def format_ncd_matrix_summary(matrix: NCDMatrix) -> str:
    """Format a summary of the NCD matrix."""
    lines = [
        "# NCD 距离矩阵摘要",
        "",
        f"- **压缩器**: {matrix.compressor}",
        f"- **对象数**: {matrix.n_objects}",
        f"- **平均距离**: {matrix.avg_distance():.4f}",
        f"- **最小距离**: {matrix.min_distance():.4f}",
        f"- **最大距离**: {matrix.max_distance():.4f}",
        "",
    ]

    if matrix.n_objects <= 30:
        lines.append("## 距离矩阵 (下三角)")
        lines.append("")
        header = "| 对象 | " + " | ".join(
            matrix.object_ids[i][:12]
            for i in range(min(8, matrix.n_objects))
        ) + " |"
        lines.append(header)
        sep = "|---|" + "|".join(["---"] * min(8, matrix.n_objects)) + "|"
        lines.append(sep)
        for i in range(min(10, matrix.n_objects)):
            row = [matrix.object_ids[i][:12]]
            for j in range(min(8, matrix.n_objects)):
                d = matrix.get_by_idx(i, j)
                row.append(f"{d:.3f}")
            lines.append("| " + " | ".join(row) + " |")
        if matrix.n_objects > 10:
            lines.append(f"| ... | ... (仅显示前10x8) |")
        lines.append("")

    return "\n".join(lines)


def format_ncd_neighbors(
    obj_id: str, neighbors: List[Tuple[str, float]],
) -> str:
    """Format nearest neighbors for an object."""
    lines = [
        f"## NCD 最近邻: `{obj_id}`",
        "",
        "| 排名 | 对象 | NCD | 相似度 (1-NCD) |",
        "|------|------|-----|----------------|",
    ]
    for rank, (nid, dist) in enumerate(neighbors, 1):
        sim = max(0.0, 1.0 - dist)
        lines.append(f"| {rank} | `{nid}` | {dist:.4f} | {sim:.4f} |")
    lines.append("")
    return "\n".join(lines)


def format_ncd_clusters(
    root: NCDCluster, threshold: float = 0.5
) -> str:
    """Format hierarchical clustering result as markdown."""
    clusters = flatten_clusters(root, threshold)
    leaves_total = sum(len(get_cluster_leaves(c)) for c in clusters)

    lines = [
        "# NCD 层次聚类",
        "",
        f"- **聚类阈值**: {threshold:.2f}",
        f"- **簇数**: {len(clusters)}",
        f"- **总叶子数**: {leaves_total}",
        "",
    ]

    for ci, cluster in enumerate(clusters, 1):
        leaves = get_cluster_leaves(cluster)
        dist_label = f" (merge@{cluster.distance:.3f})" if not cluster.is_leaf else ""
        lines.append(f"### 簇 {ci}{dist_label} ({len(leaves)} 个对象)")
        for leaf in leaves[:10]:
            lines.append(f"  - `{leaf}`")
        if len(leaves) > 10:
            lines.append(f"  ... 另有 {len(leaves) - 10} 个")
        lines.append("")

    # Dendrogram as text tree
    lines.append("### 聚类树")
    lines.append("")
    lines.append("```")
    lines.append(_format_dendrogram_node(root, "", True, max_depth=30))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _format_dendrogram_node(
    node: NCDCluster, indent: str, is_last: bool, max_depth: int,
) -> str:
    """Text-based dendrogram rendering."""
    if max_depth <= 0:
        return indent + "..."
    prefix = "└── " if is_last else "├── "
    if node.is_leaf:
        label = node.label
        if len(label) > 50:
            label = "..." + label[-47:]
        return indent + prefix + label
    dist_info = f"d={node.distance:.3f}"
    lines = [indent + prefix + dist_info]
    child_indent = indent + ("    " if is_last else "│   ")
    for i, child in enumerate(node.children):
        child_last = (i == len(node.children) - 1)
        lines.append(
            _format_dendrogram_node(child, child_indent, child_last, max_depth - 1)
        )
    return "\n".join(lines)


def format_ncd_invariant_comparison(comparison: Dict[str, Any]) -> str:
    """Format the NCD vs invariant cross-validation result."""
    if "error" in comparison:
        return f"Error: {comparison['error']}"

    lines = [
        "# NCD vs 不变量交叉验证",
        "",
        f"- **比较对数**: {comparison['n_compared']}",
        f"- **Pearson相关系数**: {comparison['pearson_correlation']}",
        f"- **平均NCD相似度**: {comparison['avg_ncd_similarity']:.4f}",
        f"- **平均不变量相似度**: {comparison['avg_invariant_similarity']:.4f}",
        f"- **解读**: {comparison['interpretation']}",
        "",
    ]

    if comparison["disagreements"]:
        lines.append("## 分歧项 (NCD与不变量分析不一致)")
        lines.append("")
        for d in comparison["disagreements"]:
            lines.append(
                f"- `{d['a']}` ↔ `{d['b']}`: "
                f"NCD={d['ncd_similarity']:.3f}, "
                f"Inv={d['invariant_similarity']:.3f}"
            )
            lines.append(f"  _{d['interpretation']}_")
        lines.append("")

    return "\n".join(lines)


def format_ncd_anomalies(anomalies: List[Dict[str, Any]]) -> str:
    """Format NCD anomaly detection results."""
    if not anomalies:
        return "未检测到NCD异常对象。"

    lines = [
        "# NCD 异常检测",
        "",
        f"**异常对象数**: {len(anomalies)}",
        "",
        "| 对象 | 平均NCD | 全局均值 | Z分数 |",
        "|------|---------|----------|-------|",
    ]
    for a in anomalies:
        lines.append(
            f"| `{a['object_id']}` | {a['mean_ncd']:.4f} "
            f"| {a['global_mean']:.4f} | {a['z_score']:.1f} |"
        )
    lines.append("")
    lines.append("> Z分数 > 2.0 表示该对象与其他所有对象的平均距离显著偏高 — 可能是独特/孤立的问题类型。")
    lines.append("")

    return "\n".join(lines)
