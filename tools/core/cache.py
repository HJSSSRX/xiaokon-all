from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
import time
import json
from pathlib import Path

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def clear(self) -> None:
        pass

class MemoryCache(CacheBackend):
    def __init__(self):
        self._cache: Dict[str, dict] = {}
    
    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry:
            if entry["expire_at"] > time.time():
                return entry["value"]
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        self._cache[key] = {
            "value": value,
            "expire_at": time.time() + ttl_seconds
        }
    
    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def exists(self, key: str) -> bool:
        return self.get(key) is not None
    
    def clear(self) -> None:
        self._cache.clear()

class RedisCache(CacheBackend):
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        if not REDIS_AVAILABLE:
            raise RuntimeError("redis-py not installed. Install with: pip install redis")
        self._client = redis.Redis(host=host, port=port, db=db)
    
    def get(self, key: str) -> Optional[Any]:
        try:
            value = self._client.get(key)
            if value:
                return json.loads(value)
        except Exception:
            pass
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        try:
            self._client.set(key, json.dumps(value), ex=ttl_seconds)
        except Exception:
            pass
    
    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception:
            pass
    
    def exists(self, key: str) -> bool:
        try:
            return self._client.exists(key) > 0
        except Exception:
            return False
    
    def clear(self) -> None:
        try:
            self._client.flushdb()
        except Exception:
            pass

class FileCache(CacheBackend):
    def __init__(self, cache_dir: str = "data/cache"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _key_to_path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._cache_dir / f"{safe_key}.json"
    
    def get(self, key: str) -> Optional[Any]:
        path = self._key_to_path(key)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data["expire_at"] > time.time():
                        return data["value"]
                    else:
                        path.unlink()
            except Exception:
                pass
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        path = self._key_to_path(key)
        data = {
            "value": value,
            "expire_at": time.time() + ttl_seconds
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    
    def delete(self, key: str) -> None:
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()
    
    def exists(self, key: str) -> bool:
        return self.get(key) is not None
    
    def clear(self) -> None:
        for f in self._cache_dir.glob("*.json"):
            f.unlink()

def create_cache(cache_type: str = "memory", **kwargs) -> CacheBackend:
    if cache_type == "redis" and REDIS_AVAILABLE:
        return RedisCache(**kwargs)
    elif cache_type == "file":
        return FileCache(**kwargs)
    else:
        return MemoryCache()

_cache_instance: Optional[CacheBackend] = None

def get_cache() -> CacheBackend:
    global _cache_instance
    if _cache_instance is None:
        from .config import load_config
        config = load_config()
        _cache_instance = create_cache(
            config.cache.type,
            host=config.cache.host,
            port=config.cache.port
        )
    return _cache_instance

def cached(ttl_seconds: int = 3600):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = f"cache_{func.__name__}_{args}_{tuple(sorted(kwargs.items()))}"
            cache = get_cache()
            
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl_seconds)
            return result
        return wrapper
    return decorator