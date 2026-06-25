"""Tests for configuration."""
import os
import pytest
from gib.config import get_config, Config


def test_config_loads():
    get_config.cache_clear()
    cfg = get_config()
    assert isinstance(cfg, Config)


def test_model_for_task():
    get_config.cache_clear()
    cfg = get_config()
    model = cfg.model_for_task("review")
    assert isinstance(model, str)


def test_model_for_unknown_task_returns_default():
    get_config.cache_clear()
    cfg = get_config()
    model = cfg.model_for_task("nonexistent_task_xyz")
    assert model == cfg.models.default


def test_api_key_from_env(monkeypatch):
    get_config.cache_clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")
    cfg = get_config()
    assert cfg.api_key == "test-key-123"
