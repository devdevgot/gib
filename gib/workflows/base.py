"""Base Workflow — абстрактный базовый класс для всех workflow."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from gib.core.state import GibState
from gib.providers.errors import CreditsExhaustedError
from gib.workflows.checkpoint import checkpoint_conn_string


class BaseWorkflow(ABC):
    """
    Базовый workflow.

    Каждый подкласс:
    1. Реализует build_graph() — возвращает StateGraph (без compile)
    2. run() — async точка входа с SQLite checkpoint для resume
    """

    @classmethod
    @abstractmethod
    def build_graph(cls):
        """Строит LangGraph StateGraph (не скомпилированный)."""
        ...

    @classmethod
    async def run(
        cls,
        initial_state: GibState,
        *,
        thread_id: str | None = None,
        resume: bool = False,
    ) -> GibState:
        """
        Запускает граф с checkpoint.

        resume=False — новый запуск с initial_state
        resume=True  — продолжить с последнего checkpoint (initial_state игнорируется)
        """
        thread_id = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        async with AsyncSqliteSaver.from_conn_string(checkpoint_conn_string()) as checkpointer:
            graph = cls.build_graph().compile(checkpointer=checkpointer)
            try:
                if resume:
                    return await graph.ainvoke(None, config)
                return await graph.ainvoke(initial_state, config)
            except CreditsExhaustedError:
                raise
            except Exception as e:
                # Propagate credit errors wrapped in node failures
                if isinstance(e.__cause__, CreditsExhaustedError):
                    raise e.__cause__ from e
                raise
