"""Node: Merge — объединяет результаты параллельных агентов.

Убирает конфликты, строит единый план изменений.
"""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import TaskType
from gib.utils import get_logger

logger = get_logger("gib.nodes.merge")

_MERGE_SYSTEM = """\
You are a Senior Lead Engineer responsible for integrating outputs from multiple specialist agents.

You receive:
1. Architectural design from an Architect
2. Implementation code from a Developer  
3. Research findings from a Researcher

Your job:
- Synthesize these into a unified, coherent implementation plan
- Resolve any conflicts between architectural design and code implementation
- Incorporate research findings and best practices into the code
- Ensure the final code is complete and consistent
- Remove duplicate or conflicting suggestions

Output a single unified implementation that:
1. Follows the architectural decisions
2. Incorporates research best practices
3. Is production-ready
"""


def _build_merge_prompt(state: GibState) -> str:
    arch = state.get("architecture_result", "")
    code = state.get("code_result", "")
    research = state.get("research_result", "")

    parts = [
        f"## Original Task\n{state.get('user_request', '')}",
    ]

    if arch:
        parts.append(f"\n## Architecture Design (from Architect)\n{arch[:4000]}")
    if code:
        parts.append(f"\n## Implementation (from Developer)\n{code[:6000]}")
    if research:
        parts.append(f"\n## Research Findings (from Researcher)\n{research[:2000]}")

    parts.append(
        "\n## Your Task"
        "\nMerge the above into a unified, complete implementation."
        "\nResolve conflicts. Apply research insights to the code."
        "\nProvide the final merged implementation."
    )

    return "\n".join(parts)


async def node_merge(state: GibState) -> dict:
    """
    LangGraph Node: объединяет результаты агентов.
    """
    # Если нет конфликтов — просто собираем
    has_arch = bool(state.get("architecture_result"))
    has_code = bool(state.get("code_result"))
    has_research = bool(state.get("research_result"))

    # Если только один агент — нечего мержить
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
            "logs": ["[Merge] Single agent output, no merge needed"],
        }

    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = router.select_model(TaskType.REVIEW)  # Claude для мержа
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
        "code_result": resp.content,  # обновляем code_result объединённым результатом
        "current_step": "merged",
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[Merge] Merged {active_count} agents with {resp.model}"],
    }
