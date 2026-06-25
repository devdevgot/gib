"""Node: Developer Agent — GPT пишет код по архитектурному плану.

Запускается параллельно с Architect и Researcher (после того как план готов).
При повторной итерации учитывает замечания ревьюера.
"""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentOutput, AgentRole, TaskType
from gib.utils import get_logger

logger = get_logger("gib.nodes.developer")

_DEVELOPER_SYSTEM = """\
You are a Senior Software Engineer. You write production-quality code.

Rules:
- Write complete, working code — not pseudocode or examples
- Follow existing code style and conventions
- Add proper error handling
- Write self-documenting code with clear variable names
- Include docstrings for public functions
- Never leave TODO comments — implement everything
- If modifying existing code, show the complete modified file

Format your response as:
1. Brief explanation of your approach
2. Complete code with file paths clearly labeled as:
   ### filename.ext
   ```language
   <code>
   ```
"""

_RETRY_SUFFIX = """\

## ⚠️ Previous Review Feedback (MUST FIX ALL)
{review_comments}

The reviewer rejected your previous implementation. Fix ALL issues listed above.
"""


def _build_developer_prompt(state: GibState) -> str:
    arch = state.get("architecture_result", "")
    files = state.get("file_contents", {})
    iteration = state.get("review_iteration", 1)
    review = state.get("review_result", "")
    comments = state.get("review_comments", [])

    # Контекст файлов
    file_context = ""
    for path, content in list(files.items())[:15]:
        file_context += f"\n### {path}\n```\n{content[:3000]}\n```\n"

    parts = [
        f"## Task\n{state.get('user_request', '')}",
        f"\n## Architecture Plan\n{arch}" if arch else "",
        f"\n## Existing Code{file_context}" if file_context else "",
    ]

    prompt = "\n".join(p for p in parts if p)

    # Добавляем замечания ревьюера при повторной попытке
    if iteration > 1 and (review or comments):
        review_text = "\n".join(comments) if comments else review[:2000]
        prompt += _RETRY_SUFFIX.format(review_comments=review_text)

    return prompt


async def node_developer(state: GibState) -> dict:
    """
    LangGraph Node: GPT пишет реализацию.
    """
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = state.get("selected_models", {}).get(
        AgentRole.DEVELOPER.value,
        router.select_model(TaskType.DEVELOPMENT)
    )
    prompt = _build_developer_prompt(state)
    iteration = state.get("review_iteration", 1)

    logger.info("[developer] Пишу код, итерация=%d, модель=%s", iteration, model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_DEVELOPER_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.15,
        max_tokens=8192,
    )

    output = AgentOutput(
        role=AgentRole.DEVELOPER,
        model_id=resp.model,
        content=resp.content,
        cost_usd=resp.cost_usd,
        latency_ms=resp.latency_ms,
        metadata={"iteration": iteration},
    )

    logger.info("[developer] Готово: %d chars, cost=$%.4f", len(resp.content), resp.cost_usd)

    return {
        "code_result": resp.content,
        "agent_outputs": [output],
        "completed_agents": [AgentRole.DEVELOPER.value],
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[Developer] Iteration {iteration}, model={resp.model}, cost=${resp.cost_usd:.4f}"],
    }
