"""Configuration loader — reads config.yaml and .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# Bundled config — ships with the package
_BUNDLED_CONFIG = Path(__file__).parent.parent.parent / "config.yaml"

_CONFIG_SEARCH_PATHS = [
    Path.cwd() / "config.yaml",
    Path.home() / ".gib" / "config.yaml",
    _BUNDLED_CONFIG,
]


def _ensure_global_config() -> None:
    """Copy bundled config.yaml to ~/.gib/ on first run so user can edit it."""
    global_cfg = Path.home() / ".gib" / "config.yaml"
    if not global_cfg.exists() and _BUNDLED_CONFIG.exists():
        global_cfg.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(_BUNDLED_CONFIG, global_cfg)


class RoutingRule(BaseModel):
    task_type: str
    model: str
    reason: str = ""


class ModelsConfig(BaseModel):
    default: str = "anthropic/claude-opus-4.8"
    fast: str = "google/gemini-2.5-flash"
    cheap: str = "deepseek/deepseek-v3.2"
    large_context: str = "google/gemini-2.5-pro"
    code: str = "openai/gpt-5.5"
    reviewer: str = "google/gemini-2.5-pro"
    docs: str = "google/gemini-2.5-pro"
    tests: str = "openai/gpt-5.5"


class OpenRouterConfig(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    timeout: int = 120
    max_retries: int = 3


class AgentsConfig(BaseModel):
    max_parallel: int = 4
    timeout: int = 300


class MemoryConfig(BaseModel):
    db_path: str = "~/.gib/memory.db"
    max_history: int = 1000
    checkpoint_db_path: str = "~/.gib/checkpoints.db"


class SecurityConfig(BaseModel):
    auto_apply: bool = False
    require_confirmation: bool = True
    show_diff: bool = True


class UIConfig(BaseModel):
    show_cost: bool = True
    show_time: bool = True
    show_model: bool = True
    show_agents: bool = True
    theme: str = "dark"


class RoutingConfig(BaseModel):
    rules: list[RoutingRule] = Field(default_factory=list)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    log_dir: str = "~/.gib/logs"


class Config(BaseModel):
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @property
    def api_key(self) -> str:
        # Always read fresh from env — never cached, so set-key works instantly
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            # Try loading ~/.gib/.env on the fly
            global_env = Path.home() / ".gib" / ".env"
            if global_env.exists():
                load_dotenv(global_env, override=True)
            key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise ValueError(
                "OPENROUTER_API_KEY не задан. Выполните: gib set-key"
            )
        return key

    def model_for_task(self, task_type: str) -> str:
        """Return the best model for a given task type based on routing rules."""
        for rule in self.routing.rules:
            if rule.task_type == task_type:
                return rule.model
        return self.models.default

    def memory_db_path(self) -> Path:
        path = Path(self.memory.db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def checkpoint_db_path(self) -> Path:
        path = Path(self.memory.checkpoint_db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def log_dir_path(self) -> Path:
        path = Path(self.logging.log_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load and cache configuration."""
    _ensure_global_config()
    raw: dict[str, Any] = {}
    for p in _CONFIG_SEARCH_PATHS:
        if p.exists():
            raw = _load_yaml(p)
            break
    return Config.model_validate(raw)
