from .config import load_config, Config
from .cache import get_cache, cached, create_cache, MemoryCache, RedisCache, FileCache
from .vector_db import get_vector_db, semantic_search, build_kb_index, FAISSVectorDB, SimpleVectorDB
from .scheduler import get_scheduler, execute_async, execute_sync, parallel_map, Task, TaskStatus, TaskPriority
from .tool_pool import get_tool_router, run_tool, run_tool_with_retry, ToolRouter, ProcessToolPool, WSLToolPool
from .http_base import BaseHandler
from .ids import next_seq_id, next_finding_id, next_question_id, next_blocker_id, next_need_id
from .utils import (
    now_str, load_yaml, save_yaml, log,
    shared_dir, shared_path, ensure_dir, repo_root,
    compute_hash, compute_dict_hash, next_seq_id,
    load_json, save_json, get_env_var, set_env_var,
    safe_call, memoize, CoreError,
    synchronized as synchronized_decorator,
)


class synchronized:
    """Context manager for lock acquire/release. Used by collab_hub.py."""
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
    'now_str', 'load_yaml', 'save_yaml', 'shared_path', 'log', 'synchronized',
    'shared_dir', 'compute_dict_hash', 'next_seq_id', 'ensure_dir', 'repo_root',
    'synchronized_decorator',
    'BaseHandler', 'next_finding_id', 'next_question_id', 'next_blocker_id', 'next_need_id',
]
