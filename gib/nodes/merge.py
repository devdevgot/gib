"""Node: Merge — объединяет результаты параллельных агентов."""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import TaskType
from gib.prompts.locale import RUSSIAN_ONLY
from gib.utils import get_logger

logger = get_logger("gib.nodes.merge")

_MERGE_SYSTEM = f"""\
Ты — ведущий инженер, отвечающий за интеграцию результатов нескольких специализированных агентов.

Ты получаешь:
1. Архитектурный дизайн от архитектора
2. Код реализации от разработчика
3. Результаты исследования от исследователя

Твоя задача:
- Синтезировать всё в единый согласованный план реализации
- Разрешить конфликты между архитектурой и кодом
- Включить выводы исследования и best practices в код
- Убедиться, что итоговый код полный и согласованный
- Убрать дубли и противоречия

Выдай единую итоговую реализацию, которая:
1. Следует архитектурным решениям
2. Учитывает результаты исследования
3. Готова к продакшену

{RUSSIAN_ONLY}
"""


def _build_merge_prompt(state: GibState) -> str:
    arch = state.get("architecture_result", "")
    code = state.get("code_result", "")
    research = state.get("research_result", "")

    parts = [
        f"## Исходная задача\n{state.get('user_request', '')}",
    ]

    if arch:
        parts.append(f"\n## Архитектура (от архитектора)\n{arch[:8000]}")
    if code:
        parts.append(f"\n## Реализация (от разработчика)\n{code[:10000]}")
    if research:
        parts.append(f"\n## Исследование (от исследователя)\n{research[:4000]}")

    parts.append(
        "\n## Твоя задача"
        "\nОбъедини всё выше в единую полную реализацию."
        "\nРазреши конфликты. Примени выводы исследования к коду."
        "\nПредоставь финальную объединённую реализацию."
    )

    return "\n".join(parts)


async def node_merge(state: GibState) -> dict:
    """LangGraph Node: объединяет результаты агентов."""
    has_arch = bool(state.get("architecture_result"))
    has_code = bool(state.get("code_result"))
    has_research = bool(state.get("research_result"))

    active_count = sum([has_arch, has_code, has_research])
    if active_count <= 1:
        final = (
            state.get("code_result")
            or state.get("architecture_result")
            or state.get("research_result")
            or ""
        )
        logger.info("[merge] Только один агент, пропускаю мерж")
        return {
            "final_output": final,
            "current_step": "merged",
            "logs": ["[Merge] Один агент, мерж не требуется"],
        }

    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = router.select_model(TaskType.REVIEW)
    prompt = _build_merge_prompt(state)

    logger.info("[merge] Объединяю результаты %d агентов, модель: %s", active_count, model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_MERGE_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.1,
        max_tokens=8192,
    )

    logger.info("[merge] Готово: %d chars, cost=$%.4f", len(resp.content), resp.cost_usd)

    return {
        "code_result": resp.content,
        "current_step": "merged",
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[Merge] Объединено {active_count} агентов с {resp.model}"],
    }
