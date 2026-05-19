from .config import load_config, Config
from .cache import get_cache, cached, create_cache, MemoryCache, RedisCache, FileCache
from .vector_db import get_vector_db, semantic_search, build_kb_index, FAISSVectorDB, SimpleVectorDB
from .scheduler import get_scheduler, execute_async, execute_sync, parallel_map, Task, TaskStatus, TaskPriority
from .tool_pool import get_tool_router, run_tool, run_tool_with_retry, ToolRouter, ProcessToolPool, WSLToolPool

import datetime
import json
import os
from pathlib import Path

def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_yaml(path, default=None):
    import yaml
    path = Path(path)
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return default

def save_yaml(path, data):
    import yaml
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

def shared_path(case_dir, filename):
    return str(Path(case_dir) / "shared" / filename)

def log(message):
    print(f"[{now_str()}] {message}")

class synchronized:
    def __init__(self, lock):
        self._lock = lock
    
    def __enter__(self):
        self._lock.acquire()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()

__all__ = [
    'load_config', 'Config',
    'get_cache', 'cached', 'create_cache', 'MemoryCache', 'RedisCache', 'FileCache',
    'get_vector_db', 'semantic_search', 'build_kb_index', 'FAISSVectorDB', 'SimpleVectorDB',
    'get_scheduler', 'execute_async', 'execute_sync', 'parallel_map', 'Task', 'TaskStatus', 'TaskPriority',
    'get_tool_router', 'run_tool', 'run_tool_with_retry', 'ToolRouter', 'ProcessToolPool', 'WSLToolPool',
    'now_str', 'load_yaml', 'save_yaml', 'shared_path', 'log', 'synchronized'
]