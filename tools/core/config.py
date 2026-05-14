#!/usr/bin/env python3
"""
Configuration management module - 统一配置管理

提供集中式配置管理，支持多种配置来源：
1. 环境变量
2. 配置文件
3. 命令行参数
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .utils import load_yaml, save_yaml, get_env_var


class ConfigManager:
    """统一配置管理器"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._config: Dict[str, Any] = {}
        self._config_files = []
        self._initialized = True
    
    def load_config(self, config_path: Optional[Path] = None) -> None:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径，默认为项目根目录的 config.yaml
        """
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"
        
        if config_path.exists():
            self._config.update(load_yaml(config_path))
            self._config_files.append(config_path)
    
    def load_from_env(self, prefix: str = "FORHACKER_") -> None:
        """
        从环境变量加载配置
        
        Args:
            prefix: 环境变量前缀
        """
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower().replace("_", ".")
                self._config[config_key] = value
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        self._config[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        
        Args:
            key: 配置键（支持点分隔，如 "feeder.storage"）
            default: 默认值
        
        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数类型配置"""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点数类型配置"""
        value = self.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔类型配置"""
        value = self.get(key, default)
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1")
        return bool(value)
    
    def get_path(self, key: str, default: Optional[Path] = None) -> Optional[Path]:
        """获取路径类型配置"""
        value = self.get(key)
        if value:
            return Path(value)
        return default
    
    def update_from_cli(self, args: Any) -> None:
        """
        从命令行参数更新配置
        
        Args:
            args: argparse.Namespace 对象
        """
        if hasattr(args, '__dict__'):
            for key, value in args.__dict__.items():
                if value is not None:
                    self.set(key, value)
    
    def save(self, path: Optional[Path] = None) -> None:
        """
        保存配置到文件
        
        Args:
            path: 保存路径，默认为首次加载的配置文件
        """
        if path is None and self._config_files:
            path = self._config_files[0]
        
        if path:
            save_yaml(path, self._config)
    
    def to_dict(self) -> Dict[str, Any]:
        """获取所有配置的字典表示"""
        return self._config.copy()


# ─── Feeder Configuration ───

class FeederConfig:
    """喂食者模块配置"""
    
    STORAGE_ENV_KEY = "FEEDER_STORAGE"
    
    def __init__(self):
        self._config = ConfigManager()
    
    @property
    def storage_path(self) -> Path:
        """获取喂食者存储路径"""
        # 优先级：环境变量 > 配置文件 > 默认路径
        custom_path = get_env_var(self.STORAGE_ENV_KEY)
        if custom_path:
            return Path(custom_path)
        
        config_path = self._config.get_path("feeder.storage")
        if config_path:
            return config_path
        
        return Path(__file__).resolve().parent.parent.parent / "data" / "feeder"
    
    @storage_path.setter
    def storage_path(self, path: Path) -> None:
        """设置喂食者存储路径"""
        os.environ[self.STORAGE_ENV_KEY] = str(path)
        self._config.set("feeder.storage", str(path))
    
    @property
    def timeout(self) -> int:
        """获取爬虫超时时间（秒）"""
        return self._config.get_int("feeder.timeout", 30)
    
    @property
    def max_retries(self) -> int:
        """获取最大重试次数"""
        return self._config.get_int("feeder.max_retries", 3)
    
    @property
    def user_agent(self) -> str:
        """获取User-Agent"""
        return self._config.get("feeder.user_agent", 
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")


# ─── Collaboration Hub Configuration ───

class HubConfig:
    """协作Hub配置"""
    
    def __init__(self):
        self._config = ConfigManager()
    
    @property
    def port(self) -> int:
        """获取Hub端口"""
        return self._config.get_int("hub.port", 8765)
    
    @property
    def bind_address(self) -> str:
        """获取绑定地址"""
        return self._config.get("hub.bind_address", "0.0.0.0")
    
    @property
    def heartbeat_timeout(self) -> int:
        """获取心跳超时时间（秒）"""
        return self._config.get_int("hub.heartbeat_timeout", 300)
    
    @property
    def answer_lock_timeout(self) -> int:
        """获取答案锁超时时间（秒）"""
        return self._config.get_int("hub.answer_lock_timeout", 300)


# ─── Global Config Instance ───

config = ConfigManager()
feeder_config = FeederConfig()
hub_config = HubConfig()


def init_config(config_path: Optional[Path] = None) -> None:
    """
    初始化配置
    
    Args:
        config_path: 配置文件路径
    """
    config.load_config(config_path)
    config.load_from_env()