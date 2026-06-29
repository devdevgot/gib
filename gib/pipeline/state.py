"""GIB Pipeline State — shared state across all LangGraph nodes."""
from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


class PipelineState(TypedDict):
    """Состояние, передаваемое между узлами графа."""

    # Входные данные
    prompt: str
    file_context: str
    error_context: str          # для gib fix — текст ошибки
    project_meta: dict[str, Any]  # сериализованный ProjectProfile

    # Выходы каждого агента
    architect_plan: str          # Claude: архитектурный план
    developer_code: str          # GLM 5.2: реализованный код
    review_result: str           # Gemini: результат ревью
    review_verdict: str          # "approved" | "needs_fix" | "rejected"

    # Итерации
    iteration: int               # текущий номер итерации (макс 2)
    max_iterations: int

    # Метрики — суммируются через add
    total_cost_usd: Annotated[float, lambda a, b: a + b]
    total_latency_ms: Annotated[int, lambda a, b: a + b]
    models_used: Annotated[list[str], lambda a, b: a + b]  # цепочка моделей

    # Финал
    final_output: str
    success: bool
