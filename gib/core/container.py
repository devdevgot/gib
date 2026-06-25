"""Dependency Injection Container — единственная точка создания зависимостей.

Все узлы получают зависимости через Container, а не создают их напрямую.
Это обеспечивает тестируемость: в тестах можно подменить любую зависимость.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gib.providers.openrouter import OpenRouterClient
    from gib.router.model_router import ModelRouter
    from gib.memory.store import MemoryStore


class Container:
    """
    Singleton DI-контейнер.
    
    Использование:
        container = Container.instance()
        client = container.openrouter_client()
    
    В тестах:
        Container.instance().override(openrouter_client=mock_client)
    """

    _instance: "Container | None" = None
    _overrides: dict = {}

    @classmethod
    def instance(cls) -> "Container":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Для тестов — сбросить синглтон."""
        cls._instance = None
        cls._overrides = {}

    def override(self, **kwargs) -> None:
        """Подменить зависимости (для тестов)."""
        self._overrides.update(kwargs)

    def openrouter_client(self) -> "OpenRouterClient":
        if "openrouter_client" in self._overrides:
            return self._overrides["openrouter_client"]
        if not hasattr(self, "_openrouter_client"):
            from gib.providers.openrouter import OpenRouterClient
            self._openrouter_client = OpenRouterClient()
        return self._openrouter_client

    def model_router(self) -> "ModelRouter":
        if "model_router" in self._overrides:
            return self._overrides["model_router"]
        if not hasattr(self, "_model_router"):
            from gib.router.model_router import ModelRouter
            self._model_router = ModelRouter()
        return self._model_router

    def memory_store(self) -> "MemoryStore":
        if "memory_store" in self._overrides:
            return self._overrides["memory_store"]
        if not hasattr(self, "_memory_store"):
            from gib.memory.store import MemoryStore
            self._memory_store = MemoryStore()
        return self._memory_store
