from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
import shlex
import subprocess
import shutil
import os
import threading
import time
from threading import Lock
from .cache import get_cache

class ToolPool(ABC):
    @abstractmethod
    def execute(self, tool_name: str, args: List[str] = None, timeout: int = 60) -> Tuple[int, str, str]:
        pass
    
    @abstractmethod
    def is_available(self, tool_name: str) -> bool:
        pass
    
    @abstractmethod
    def get_tool_path(self, tool_name: str) -> Optional[str]:
        pass

class ProcessToolPool(ToolPool):
    def __init__(self):
        self._tool_paths: Dict[str, str] = {}
        self._available_tools: Dict[str, bool] = {}
        self._lock = Lock()
        self._cache = get_cache()
    
    def _find_tool(self, tool_name: str) -> Optional[str]:
        cache_key = f"tool_path_{tool_name}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        path = shutil.which(tool_name)
        if path:
            self._cache.set(cache_key, path, ttl_seconds=3600)
            return path
        
        return None
    
    def execute(self, tool_name: str, args: List[str] = None, timeout: int = 60) -> Tuple[int, str, str]:
        tool_path = self._find_tool(tool_name)
        if not tool_path:
            return -1, "", f"Tool '{tool_name}' not found"
        
        cmd = [tool_path] + (args or [])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -2, "", f"Timeout after {timeout} seconds"
        except Exception as e:
            return -3, "", str(e)
    
    def is_available(self, tool_name: str) -> bool:
        return self._find_tool(tool_name) is not None
    
    def get_tool_path(self, tool_name: str) -> Optional[str]:
        return self._find_tool(tool_name)

class WSLToolPool(ToolPool):
    def __init__(self):
        self._cache = get_cache()
    
    def execute(self, tool_name: str, args: List[str] = None, timeout: int = 60) -> Tuple[int, str, str]:
        safe_tool = shlex.quote(tool_name)
        safe_args = " ".join(shlex.quote(a) for a in (args or []))
        wsl_args = ["wsl", "--", "bash", "-lc", f"{safe_tool} {safe_args}"]
        
        try:
            result = subprocess.run(
                wsl_args,
                capture_output=True,
                timeout=timeout,
                text=False
            )
            
            stdout = self._decode_output(result.stdout)
            stderr = self._decode_output(result.stderr)
            
            return result.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -2, "", f"Timeout after {timeout} seconds"
        except Exception as e:
            return -3, "", str(e)
    
    def _decode_output(self, raw: bytes) -> str:
        if not raw:
            return ""
        if raw[:2] == b"\xff\xfe":
            try:
                return raw.decode("utf-16-le", errors="replace").lstrip("\ufeff")
            except Exception:
                pass
        if raw[:3] == b"\xef\xbb\xbf":
            return raw[3:].decode("utf-8", errors="replace")
        try:
            return raw.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return raw.decode("gbk", errors="replace")
    
    def is_available(self, tool_name: str) -> bool:
        cache_key = f"wsl_tool_available_{tool_name}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            result = subprocess.run(
                ["wsl", "--", "bash", "-lc", f"which {shlex.quote(tool_name)}"],
                capture_output=True,
                timeout=10
            )
            available = result.returncode == 0
            self._cache.set(cache_key, available, ttl_seconds=3600)
            return available
        except Exception:
            return False

    def get_tool_path(self, tool_name: str) -> Optional[str]:
        cache_key = f"wsl_tool_path_{tool_name}"
        cached = self._cache.get(cache_key)
        if cached:
            return f"WSL:{cached}"

        try:
            result = subprocess.run(
                ["wsl", "--", "bash", "-lc", f"which {shlex.quote(tool_name)}"],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                path = self._decode_output(result.stdout).strip()
                if path:
                    self._cache.set(cache_key, path, ttl_seconds=3600)
                    return f"WSL:{path}"
        except Exception:
            pass
        return None

class ToolRouter:
    def __init__(self):
        self._native_pool = ProcessToolPool()
        self._wsl_pool = WSLToolPool()
        self._tool_mapping: Dict[str, ToolPool] = {}
    
    def register_tool(self, tool_name: str, pool: ToolPool):
        self._tool_mapping[tool_name] = pool
    
    def execute(self, tool_name: str, args: List[str] = None, timeout: int = 60) -> Tuple[int, str, str]:
        if tool_name in self._tool_mapping:
            return self._tool_mapping[tool_name].execute(tool_name, args, timeout)
        
        if self._native_pool.is_available(tool_name):
            return self._native_pool.execute(tool_name, args, timeout)
        
        if self._wsl_pool.is_available(tool_name):
            return self._wsl_pool.execute(tool_name, args, timeout)
        
        return -1, "", f"Tool '{tool_name}' not available"
    
    def is_available(self, tool_name: str) -> bool:
        if tool_name in self._tool_mapping:
            return self._tool_mapping[tool_name].is_available(tool_name)
        return self._native_pool.is_available(tool_name) or self._wsl_pool.is_available(tool_name)
    
    def get_tool_path(self, tool_name: str) -> Optional[str]:
        if tool_name in self._tool_mapping:
            return self._tool_mapping[tool_name].get_tool_path(tool_name)
        
        path = self._native_pool.get_tool_path(tool_name)
        if path:
            return path
        return self._wsl_pool.get_tool_path(tool_name)

_tool_router_instance: Optional[ToolRouter] = None
_tool_router_lock = threading.Lock()

def get_tool_router() -> ToolRouter:
    global _tool_router_instance
    if _tool_router_instance is not None:
        return _tool_router_instance

    with _tool_router_lock:
        if _tool_router_instance is not None:
            return _tool_router_instance
        _tool_router_instance = ToolRouter()
        return _tool_router_instance

def run_tool(tool_name: str, *args, timeout: int = 60) -> Dict[str, Any]:
    router = get_tool_router()
    code, stdout, stderr = router.execute(tool_name, list(args), timeout)
    
    return {
        "tool": tool_name,
        "args": args,
        "return_code": code,
        "stdout": stdout,
        "stderr": stderr,
        "success": code == 0
    }

def run_tool_with_retry(tool_name: str, *args, timeout: int = 60, retries: int = 2) -> Dict[str, Any]:
    last_error = None
    
    for attempt in range(retries + 1):
        result = run_tool(tool_name, *args, timeout=timeout)
        if result["success"]:
            return result
        last_error = result["stderr"]
        if attempt < retries:
            time.sleep(2 ** attempt)
    
    return {
        "tool": tool_name,
        "args": args,
        "return_code": -1,
        "stdout": "",
        "stderr": f"Failed after {retries + 1} attempts. Last error: {last_error}",
        "success": False
    }