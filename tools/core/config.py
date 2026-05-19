from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml

@dataclass
class DatabaseConfig:
    type: str = "sqlite"
    path: str = "data/example_db.sqlite"
    host: str = "localhost"
    port: int = 5432
    database: str = "forhacker"
    username: str = ""
    password: str = ""

@dataclass
class CacheConfig:
    type: str = "memory"
    host: str = "localhost"
    port: int = 6379
    ttl_seconds: int = 3600

@dataclass
class VectorDBConfig:
    enabled: bool = True
    type: str = "faiss"
    path: str = "data/vector_index"
    host: str = "localhost"
    port: int = 19530

@dataclass
class HubConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    workers: int = 4
    timeout_seconds: int = 30

@dataclass
class ToolConfig:
    manifest_path: str = "tools/manifest.yaml"
    install_timeout: int = 300
    check_interval: int = 60

@dataclass
class KBConfig:
    root_path: str = "knowledge"
    max_results: int = 10
    similarity_threshold: float = 0.7

@dataclass
class SchedulerConfig:
    enabled: bool = True
    max_workers: int = 8
    task_timeout: int = 300
    retry_attempts: int = 3

@dataclass
class Config:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    vector_db: VectorDBConfig = field(default_factory=VectorDBConfig)
    hub: HubConfig = field(default_factory=HubConfig)
    tool: ToolConfig = field(default_factory=ToolConfig)
    kb: KBConfig = field(default_factory=KBConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

_config_instance: Optional[Config] = None

def load_config(path: Optional[str] = None) -> Config:
    global _config_instance
    if _config_instance is not None:
        return _config_instance
    
    config_path = Path(path or "config/config.yaml")
    config = Config()
    
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data:
                _apply_dict_to_config(data, config)
    
    _config_instance = config
    return config

def _apply_dict_to_config(data: Dict[str, Any], config: Config):
    for key, value in data.items():
        if hasattr(config, key):
            attr = getattr(config, key)
            if isinstance(attr, (DatabaseConfig, CacheConfig, VectorDBConfig, 
                                HubConfig, ToolConfig, KBConfig, SchedulerConfig)):
                if isinstance(value, dict):
                    _apply_dict_to_config(value, attr)
            else:
                setattr(config, key, value)