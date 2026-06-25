"""Node: Architect Agent — Claude проектирует архитектуру решения.

Запускается параллельно с Developer и Researcher.
"""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentOutput, AgentRole, TaskType
from gib.utils import get_logger

logger = get_logger("gib.nodes.architect")

_ARCHITECT_SYSTEM = """\
You are a Senior Software Architect with 15+ years of experience.

Your responsibility: design a clean, scalable architectural solution.

Focus on:
- Component breakdown and boundaries
- Data flow and API contracts
- Design patterns (SOLID, DRY, KISS)
- Scalability and maintainability
- Potential edge cases and failure modes

Be concrete and specific. Provide:
1. Architecture overview
2. Component list with responsibilities
3. Data models / interfaces
4. Implementation sequence
5. Potential risks and mitigations

Do NOT write implementation code — only architectural decisions.
"""


def _build_architect_prompt(state: GibState) -> str:
    ctx = state.get("project_context", {})
    files = state.get("file_contents", {})
    plan = state.get("execution_plan", "")

    # Компонуем контекст файлов
    file_context = ""
    for path, content in list(files.items())[:10]:
        file_context += f"\n### {path}\n```\n{content[:2000]}\n```\n"

    parts = [
        f"## Task\n{state.get('user_request', '')}",
        f"\n## Execution Plan\n{plan}" if plan else "",
        f"\n## Project Stack\nLanguage: {ctx.get('language', 'Unknown')}",
        f"Frameworks: {', '.join(ctx.get('frameworks', []))}",
        f"\n## Relevant Code{file_context}" if file_context else "",
    ]

    return "\n".join(p for p in parts if p)


async def node_architect(state: GibState) -> dict:
    """
    LangGraph Node: Claude проектирует архитектуру.
    Запускается в параллельной ветке.
    """
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
        "logs": [f"[Architect] Completed with {resp.model}, cost=${resp.cost_usd:.4f}"],
    }
