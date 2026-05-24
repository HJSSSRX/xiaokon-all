#!/usr/bin/env python3
"""
Core utilities module - 通用工具函数库

提供所有工具共享的基础功能，消除代码重复。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml  # pyyaml is a core dependency (see requirements.txt)


# ─── Time Utilities ───

def now_str(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """获取当前时间字符串"""
    return datetime.datetime.now().strftime(format)


def now_iso() -> str:
    """获取ISO格式时间字符串"""
    return datetime.datetime.now().isoformat()


def parse_datetime(dt_str: str) -> datetime.datetime:
    """解析时间字符串"""
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return datetime.datetime.now()


# ─── YAML I/O ───

def load_yaml(path: Union[str, Path], default: Any = None) -> Any:
    """
    安全加载YAML文件
    
    Args:
        path: 文件路径
        default: 文件不存在或解析失败时返回的默认值
    
    Returns:
        YAML数据，默认返回空列表
    """
    path = Path(path)
    if not path.exists():
        return default if default is not None else []
    
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if data is not None else (default if default is not None else [])
    except Exception:
        return default if default is not None else []


def save_yaml(path: Union[str, Path], data: Any, **kwargs) -> None:
    """
    安全保存YAML文件
    
    Args:
        path: 文件路径
        data: 要保存的数据
        kwargs: 传递给yaml.dump的额外参数
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    default_kwargs = {
        "allow_unicode": True,
        "default_flow_style": False,
        "sort_keys": False
    }
    default_kwargs.update(kwargs)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, **default_kwargs)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_path), str(path))


def load_yaml_str(content: str, default: Any = None) -> Any:
    """Parse YAML from a string. Safe wrapper around yaml.safe_load."""
    try:
        data = yaml.safe_load(content)
        return data if data is not None else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


# ─── JSON I/O ───

def load_json(path: Union[str, Path], default: Any = None) -> Any:
    """安全加载JSON文件"""
    path = Path(path)
    if not path.exists():
        return default if default is not None else {}
    
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def save_json(path: Union[str, Path], data: Any, indent: int = 2) -> None:
    """安全保存JSON文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


# ─── Hash Utilities ───

def compute_hash(content: str, algorithm: str = "sha256") -> str:
    """计算字符串的哈希值"""
    h = hashlib.new(algorithm)
    h.update(content.encode("utf-8"))
    return h.hexdigest()


def compute_dict_hash(data: Dict, key_fields: Optional[List[str]] = None) -> str:
    """
    计算字典内容的哈希值，用于重复检测
    
    Args:
        data: 字典数据
        key_fields: 需要考虑的关键字段列表，None表示全部字段
    
    Returns:
        哈希值字符串
    """
    if not isinstance(data, dict):
        return ""
    
    if key_fields:
        content = "|".join(str(data.get(k, "")) for k in sorted(key_fields))
    else:
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    
    return compute_hash(content)


# ─── Path Utilities ───

def ensure_dir(path: Union[str, Path]) -> Path:
    """确保目录存在，不存在则创建"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def shared_path(case_dir: Union[str, Path], name: str) -> Path:
    """获取共享目录下的文件路径"""
    return ensure_dir(Path(case_dir) / "shared") / name


def shared_dir(case_dir: Union[str, Path]) -> Path:
    """获取共享目录路径"""
    return ensure_dir(Path(case_dir) / "shared")


def repo_root() -> Path:
    """获取项目根目录路径"""
    return Path(__file__).resolve().parent.parent.parent


# ─── Sequence ID Generation ───

def next_seq_id(items: List[Dict], prefix: str, key: str = "id") -> str:
    """
    生成下一个序列号ID
    
    Args:
        items: 现有项目列表
        prefix: ID前缀（如 "F", "Q", "B"）
        key: ID字段名
    
    Returns:
        新的ID字符串（如 "F001", "Q002"）
    """
    pat = re.compile(rf"^{prefix}(\d+)$")
    nums = []
    for it in items:
        if isinstance(it, dict):
            m = pat.match(str(it.get(key, "")))
            if m:
                nums.append(int(m.group(1)))
    return f"{prefix}{max(nums, default=0) + 1:03d}"


# ─── Validation ───

def validate_path(path: Union[str, Path], whitelist_pattern: Optional[str] = None) -> bool:
    """
    验证路径安全性，防止路径遍历攻击
    
    Args:
        path: 要验证的路径
        whitelist_pattern: 可选的白名单正则表达式
    
    Returns:
        是否安全
    """
    path = Path(path).resolve()
    
    if whitelist_pattern:
        return bool(re.match(whitelist_pattern, str(path)))
    
    # 基础安全检查：不允许 .. 
    return ".." not in str(path)


# ─── Logging ───

def log(message: str, level: str = "INFO", prefix: str = "") -> None:
    """
    统一日志输出
    
    Args:
        message: 日志消息
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        prefix: 额外前缀
    """
    ts = now_str()
    level = level.upper()
    
    color_map = {
        "DEBUG": "\033[94m",
        "INFO": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "RESET": "\033[0m"
    }
    
    if sys.stdout.isatty():
        print(f"{color_map.get(level, '')}[{ts}] [{level}] {prefix}{message}{color_map['RESET']}")
    else:
        print(f"[{ts}] [{level}] {prefix}{message}")


# ─── Decorators ───

def synchronized(func: Callable) -> Callable:
    """线程同步装饰器"""
    lock = threading.Lock()
    
    def wrapper(*args, **kwargs):
        with lock:
            return func(*args, **kwargs)
    return wrapper


def memoize(func: Callable) -> Callable:
    """简单的记忆化装饰器"""
    cache = {}
    
    def wrapper(*args):
        if args not in cache:
            cache[args] = func(*args)
        return cache[args]
    return wrapper


# ─── Environment ───

def get_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """获取环境变量"""
    return os.environ.get(name, default)


def set_env_var(name: str, value: str) -> None:
    """设置环境变量"""
    os.environ[name] = value


# ─── Error Handling ───

class CoreError(Exception):
    """核心模块异常"""
    pass


def safe_call(func: Callable, *args, default=None, **kwargs) -> Any:
    """
    安全调用函数，捕获异常返回默认值
    
    Args:
        func: 要调用的函数
        args: 位置参数
        default: 异常时返回的默认值
        kwargs: 关键字参数
    
    Returns:
        函数返回值或默认值
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return default