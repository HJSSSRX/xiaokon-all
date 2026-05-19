from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    TRANSFORMER_AVAILABLE = True
except ImportError:
    TRANSFORMER_AVAILABLE = False

class VectorDB(ABC):
    @abstractmethod
    def add(self, texts: List[str], metadata: Optional[List[Dict]] = None) -> None:
        pass
    
    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> List[Tuple[float, Dict]]:
        pass
    
    @abstractmethod
    def save(self, path: str) -> None:
        pass
    
    @abstractmethod
    def load(self, path: str) -> None:
        pass
    
    @abstractmethod
    def count(self) -> int:
        pass

class FAISSVectorDB(VectorDB):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if not FAISS_AVAILABLE:
            raise RuntimeError("faiss not installed. Install with: pip install faiss-cpu")
        if not TRANSFORMER_AVAILABLE:
            raise RuntimeError("sentence-transformers not installed. Install with: pip install sentence-transformers")
        
        self._model = SentenceTransformer(model_name)
        self._index = None
        self._metadata = []
    
    def _ensure_index(self, dimension: int):
        if self._index is None:
            self._index = faiss.IndexFlatL2(dimension)
    
    def add(self, texts: List[str], metadata: Optional[List[Dict]] = None) -> None:
        embeddings = self._model.encode(texts)
        self._ensure_index(embeddings.shape[1])
        self._index.add(np.array(embeddings, dtype=np.float32))
        
        if metadata:
            self._metadata.extend(metadata)
        else:
            self._metadata.extend([{"text": t} for t in texts])
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[float, Dict]]:
        if self._index is None or self._index.ntotal == 0:
            return []
        
        query_embedding = self._model.encode([query])
        distances, indices = self._index.search(np.array(query_embedding, dtype=np.float32), top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self._metadata):
                results.append((float(distances[0][i]), self._metadata[idx]))
        
        return sorted(results, key=lambda x: x[0])
    
    def save(self, path: str) -> None:
        if self._index is not None:
            faiss.write_index(self._index, path + ".index")
            import json
            with open(path + ".metadata", "w", encoding="utf-8") as f:
                json.dump(self._metadata, f)
    
    def load(self, path: str) -> None:
        index_path = path + ".index"
        metadata_path = path + ".metadata"
        
        if Path(index_path).exists():
            self._index = faiss.read_index(index_path)
        
        if Path(metadata_path).exists():
            import json
            with open(metadata_path, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)
    
    def count(self) -> int:
        return self._index.ntotal if self._index else 0

class SimpleVectorDB(VectorDB):
    def __init__(self):
        self._embeddings = []
        self._metadata = []
    
    def _simple_encode(self, text: str):
        words = text.lower().split()
        hash_values = [hash(w) % 1000 for w in words[:100]]
        
        if NUMPY_AVAILABLE:
            vector = np.zeros(100)
            for i, h in enumerate(hash_values):
                vector[i % 100] += h / 1000.0
            norm = np.linalg.norm(vector)
            return vector / norm if norm > 0 else vector
        else:
            vector = [0.0] * 100
            for i, h in enumerate(hash_values):
                vector[i % 100] += h / 1000.0
            norm = sum(v * v for v in vector) ** 0.5
            return [v / norm for v in vector] if norm > 0 else vector
    
    def _distance(self, vec1, vec2):
        if NUMPY_AVAILABLE:
            return np.linalg.norm(vec1 - vec2)
        else:
            return sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5
    
    def add(self, texts: List[str], metadata: Optional[List[Dict]] = None) -> None:
        for text in texts:
            self._embeddings.append(self._simple_encode(text))
        
        if metadata:
            self._metadata.extend(metadata)
        else:
            self._metadata.extend([{"text": t} for t in texts])
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[float, Dict]]:
        if not self._embeddings:
            return []
        
        query_vec = self._simple_encode(query)
        results = []
        
        for i, emb in enumerate(self._embeddings):
            distance = self._distance(query_vec, emb)
            results.append((distance, self._metadata[i]))
        
        return sorted(results, key=lambda x: x[0])[:top_k]
    
    def save(self, path: str) -> None:
        data = {
            "embeddings": [list(e) if hasattr(e, 'tolist') else e for e in self._embeddings],
            "metadata": self._metadata
        }
        import json
        with open(path + ".json", "w", encoding="utf-8") as f:
            json.dump(data, f)
    
    def load(self, path: str) -> None:
        import json
        path = path + ".json"
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._embeddings = [list(e) for e in data["embeddings"]]
                self._metadata = data["metadata"]
    
    def count(self) -> int:
        return len(self._embeddings)

def create_vector_db(db_type: str = "faiss", **kwargs) -> VectorDB:
    if db_type == "faiss" and FAISS_AVAILABLE and TRANSFORMER_AVAILABLE:
        return FAISSVectorDB(**kwargs)
    else:
        return SimpleVectorDB()

_vector_db_instance: Optional[VectorDB] = None

def get_vector_db() -> VectorDB:
    global _vector_db_instance
    if _vector_db_instance is None:
        from .config import load_config
        config = load_config()
        _vector_db_instance = create_vector_db(
            config.vector_db.type
        )
        index_path = str(Path(config.vector_db.path))
        _vector_db_instance.load(index_path)
    return _vector_db_instance

def build_kb_index(kb_root: str):
    from pathlib import Path
    vector_db = get_vector_db()
    kb_path = Path(kb_root)
    
    if not kb_path.exists():
        return
    
    texts = []
    metadata = []
    
    for f in kb_path.rglob("*.md"):
        if f.name.startswith("_"):
            continue
        try:
            content = f.read_text(encoding="utf-8")
            texts.append(content[:5000])
            metadata.append({
                "path": str(f),
                "filename": f.name,
                "type": "markdown"
            })
        except Exception:
            pass
    
    for f in kb_path.rglob("*.yaml"):
        if f.name.startswith("_"):
            continue
        try:
            content = f.read_text(encoding="utf-8")
            texts.append(content[:5000])
            metadata.append({
                "path": str(f),
                "filename": f.name,
                "type": "yaml"
            })
        except Exception:
            pass
    
    if texts:
        vector_db.add(texts, metadata)
        from .config import load_config
        config = load_config()
        index_path = str(Path(config.vector_db.path))
        vector_db.save(index_path)

def semantic_search(query: str, top_k: int = 10) -> List[Dict]:
    vector_db = get_vector_db()
    results = vector_db.search(query, top_k)
    
    formatted = []
    for distance, meta in results:
        score = 1.0 - min(distance, 1.0) if distance < 10 else 0.0
        formatted.append({
            "score": score,
            "path": meta.get("path", ""),
            "filename": meta.get("filename", ""),
            "type": meta.get("type", ""),
            "text": meta.get("text", "")[:200]
        })
    
    return formatted