"""Node: Researcher Agent — Gemini проверяет документацию и best practices.

Запускается параллельно с Architect и Developer.
Ищет breaking changes, deprecated APIs, актуальные паттерны.
"""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentOutput, AgentRole, TaskType
from gib.utils import get_logger

logger = get_logger("gib.nodes.researcher")

_RESEARCHER_SYSTEM = """\
You are a Technical Researcher specializing in software best practices and documentation.

Your job:
1. Identify relevant libraries, frameworks, and APIs mentioned in the task
2. Check for known breaking changes, deprecations, or version compatibility issues
3. Find current best practices for the detected technology stack
4. Identify potential security vulnerabilities in the approach
5. Suggest proven patterns and alternatives

Be specific: include version numbers, official documentation references, and concrete examples.
Focus on what could go wrong and how to prevent it.
"""


def _build_researcher_prompt(state: GibState) -> str:
    ctx = state.get("project_context", {})
    stack = state.get("detected_stack", {})
    deps = state.get("dependencies_raw", "")[:3000]
    arch = state.get("architecture_result", "")[:2000]

    parts = [
        f"## Task to Research\n{state.get('user_request', '')}",
        f"\n## Tech Stack\nLanguage: {ctx.get('language', 'Unknown')}",
        f"Frameworks: {', '.join(stack.get('frameworks', []))}",
        f"\n## Dependencies\n{deps}" if deps else "",
        f"\n## Proposed Architecture\n{arch}" if arch else "",
        (
            "\n## Research Focus"
            "\n1. Are there breaking changes in recent versions of used libraries?"
            "\n2. What are current best practices for this stack?"
            "\n3. Are there security concerns with this approach?"
            "\n4. What alternative patterns should be considered?"
            "\n5. Any gotchas or common mistakes to avoid?"
        ),
    ]

    return "\n".join(p for p in parts if p)


async def node_researcher(state: GibState) -> dict:
    """
    LangGraph Node: Gemini исследует best practices и документацию.
    """
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
        "logs": [f"[Researcher] Completed with {resp.model}"],
    }
