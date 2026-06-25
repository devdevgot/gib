"""Node: Researcher Agent — проверяет документацию и best practices."""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentOutput, AgentRole, TaskType
from gib.prompts.locale import RUSSIAN_ONLY
from gib.utils import get_logger

logger = get_logger("gib.nodes.researcher")

_RESEARCHER_SYSTEM = f"""\
Ты — технический исследователь, специализирующийся на best practices и документации.

Твои задачи:
1. Определить релевантные библиотеки, фреймворки и API из задачи
2. Проверить breaking changes, deprecated API и совместимость версий
3. Найти актуальные best practices для обнаруженного стека
4. Выявить потенциальные уязвимости в предлагаемом подходе
5. Предложить проверенные паттерны и альтернативы

Будь конкретным: указывай версии, ссылки на документацию и примеры.
Сфокусируйся на том, что может пойти не так и как это предотвратить.

{RUSSIAN_ONLY}
"""


def _build_researcher_prompt(state: GibState) -> str:
    ctx = state.get("project_context", {})
    stack = state.get("detected_stack", {})
    deps = state.get("dependencies_raw", "")[:5000]
    arch = state.get("architecture_result", "")[:4000]
    session_context = state.get("session_context", "")
    relevant_files: list[str] = state.get("relevant_files", [])
    file_contents: dict[str, str] = state.get("file_contents", {})

    file_context = ""
    paths = relevant_files or list(file_contents.keys())[:15]
    for path in paths:
        content = file_contents.get(path, "")
        if not content:
            continue
        preview = content[:8000]
        if len(content) > 8000:
            preview += f"\n\n... [обрезано, всего {len(content)} символов]"
        file_context += f"\n### {path}\n```\n{preview}\n```\n"

    parts = [
        f"## Задача для исследования\n{state.get('user_request', '')}",
    ]
    if session_context:
        parts.append(f"\n## Память проекта\n{session_context[:6000]}")
    parts.extend([
        f"\n## Технологический стек\nЯзык: {ctx.get('language', 'Неизвестно')}",
        f"Фреймворки: {', '.join(stack.get('frameworks', []))}",
        f"\n## Зависимости\n{deps}" if deps else "",
        f"\n## Предлагаемая архитектура\n{arch}" if arch else "",
        f"\n## Релевантный код{file_context}" if file_context else "",
        (
            "\n## Фокус исследования"
            "\n1. Есть ли breaking changes в недавних версиях используемых библиотек?"
            "\n2. Какие актуальные best practices для этого стека?"
            "\n3. Есть ли проблемы безопасности в этом подходе?"
            "\n4. Какие альтернативные паттерны стоит рассмотреть?"
            "\n5. Какие типичные ошибки и подводные камни?"
        ),
    ])

    return "\n".join(p for p in parts if p)


async def node_researcher(state: GibState) -> dict:
    """LangGraph Node: исследует best practices и документацию."""
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = state.get("selected_models", {}).get(
        AgentRole.RESEARCHER.value,
        router.select_model(TaskType.RESEARCH)
    )
    prompt = _build_researcher_prompt(state)

    logger.info("[researcher] Исследую best practices, модель: %s", model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_RESEARCHER_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.2,
        max_tokens=4096,
    )

    output = AgentOutput(
        role=AgentRole.RESEARCHER,
        model_id=resp.model,
        content=resp.content,
        cost_usd=resp.cost_usd,
        latency_ms=resp.latency_ms,
    )

    logger.info("[researcher] Готово: %d chars", len(resp.content))

    return {
        "research_result": resp.content,
        "agent_outputs": [output],
        "completed_agents": [AgentRole.RESEARCHER.value],
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[Researcher] Завершено с {resp.model}"],
    }
