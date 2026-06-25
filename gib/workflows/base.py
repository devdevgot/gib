"""Base Workflow — абстрактный базовый класс для всех workflow."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from gib.core.state import GibState


class BaseWorkflow(ABC):
    """
    Базовый workflow.
    
    Каждый подкласс:
    1. Реализует build_graph() — возвращает скомпилированный граф
    2. Реализует run() — async точка входа
    """

    _graph = None  # Синглтон скомпилированного графа

    @classmethod
    def get_graph(cls):
        """Синглтон — компилируем граф один раз."""
        if cls._graph is None:
            cls._graph = cls.build_graph()
        return cls._graph

    @classmethod
    @abstractmethod
    def build_graph(cls):
        """Строит и компилирует LangGraph StateGraph."""
        ...

    @classmethod
    async def run(cls, initial_state: GibState) -> GibState:
        """Запускает граф с начальным состоянием."""
        graph = cls.get_graph()
        return await graph.ainvoke(initial_state)
