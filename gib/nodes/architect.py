"""Node: Architect Agent — проектирует архитектуру решения."""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentOutput, AgentRole, TaskType
from gib.prompts.locale import RUSSIAN_ONLY
from gib.utils import get_logger

logger = get_logger("gib.nodes.architect")

_ARCHITECT_SYSTEM = f"""\
Ты — ведущий архитектор ПО с 15+ годами опыта.

Твоя задача: спроектировать чистое, масштабируемое архитектурное решение.

Сфокусируйся на:
- разбиении на компоненты и границы ответственности
- потоках данных и контрактах API
- паттернах проектирования (SOLID, DRY, KISS)
- масштабируемости и сопровождаемости
- краевых случаях и режимах отказа

Будь конкретным. Предоставь:
1. Обзор архитектуры
2. Список компонентов с обязанностями
3. Модели данных / интерфейсы
4. Порядок реализации (какие файлы менять и в какой последовательности)
5. Риски и способы их снижения

Не пиши код реализации — только архитектурные решения.

{RUSSIAN_ONLY}
"""


def _build_architect_prompt(state: GibState) -> str:
    ctx = state.get("project_context", {})
    relevant_files: list[str] = state.get("relevant_files", [])
    file_contents: dict[str, str] = state.get("file_contents", {})
    plan = state.get("execution_plan", "")
    session_context = state.get("session_context", "")

    if relevant_files:
        files_list = "\n".join(f"  - {f}" for f in relevant_files)
        relevant_section = f"\n## Релевантные файлы\n{files_list}"
    else:
        relevant_section = ""

    file_context = ""
    for path in relevant_files:
        content = file_contents.get(path, "")
        if not content:
            continue
        preview = content[:6000 if state.get("metadata", {}).get("free_mode") else 10000]
        if len(content) > 10000:
            preview += f"\n\n... [обрезано, всего {len(content)} символов]"
        file_context += f"\n### {path}\n```\n{preview}\n```\n"

    if not file_context and file_contents:
        for path, content in list(file_contents.items())[:10]:
            file_context += f"\n### {path}\n```\n{content[:3000]}\n```\n"

    parts = [
        f"## Задача\n{state.get('user_request', '')}",
        f"\n{session_context}" if session_context else "",
        f"\n## План выполнения\n{plan}" if plan else "",
        f"\n## Стек проекта\nЯзык: {ctx.get('language', 'Неизвестно')}",
        f"Фреймворки: {', '.join(ctx.get('frameworks', []))}",
        relevant_section,
        f"\n## Релевантный код{file_context}" if file_context else "",
    ]

    return "\n".join(p for p in parts if p)


async def node_architect(state: GibState) -> dict:
    """LangGraph Node: проектирует архитектуру."""
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = state.get("selected_models", {}).get(
        AgentRole.ARCHITECT.value,
        router.select_model(TaskType.ARCHITECTURE)
    )
    prompt = _build_architect_prompt(state)

    logger.info("[architect] Проектирую архитектуру, модель: %s", model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_ARCHITECT_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.3,
        max_tokens=6144,
    )

    output = AgentOutput(
        role=AgentRole.ARCHITECT,
        model_id=resp.model,
        content=resp.content,
        cost_usd=resp.cost_usd,
        latency_ms=resp.latency_ms,
    )

    logger.info("[architect] Готово: %d chars, cost=$%.4f", len(resp.content), resp.cost_usd)

    return {
        "architecture_result": resp.content,
        "agent_outputs": [output],
        "completed_agents": [AgentRole.ARCHITECT.value],
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[Architect] Завершено с {resp.model}, стоимость=${resp.cost_usd:.4f}"],
    }
