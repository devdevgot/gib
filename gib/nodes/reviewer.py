"""Node: Reviewer — Claude проводит код-ревью.

Проверяет архитектуру, качество, SOLID, naming, performance, maintainability.
Выносит вердикт: approved / needs_fix / rejected.
"""
from __future__ import annotations

import re

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentOutput, AgentRole, ReviewVerdict, TaskType
from gib.utils import get_logger

logger = get_logger("gib.nodes.reviewer")

_REVIEWER_SYSTEM = """\
You are a Principal Software Engineer conducting a thorough code review.

Review criteria:
1. **Architecture** — SOLID principles, separation of concerns, dependency injection
2. **Code Quality** — readability, naming, documentation, complexity
3. **Performance** — algorithmic efficiency, unnecessary allocations, N+1 queries
4. **Error Handling** — proper exception handling, edge cases, null safety
5. **Maintainability** — testability, extensibility, coupling
6. **Correctness** — logic errors, race conditions, data consistency

Verdict format (REQUIRED at the start of your response):
- ✅ APPROVED — ready for production
- ⚠️ NEEDS_FIX — has issues that must be fixed (list them)
- ❌ REJECTED — fundamental problems requiring redesign

After the verdict:
- List specific issues with file/line references where possible
- Prioritize: CRITICAL > HIGH > MEDIUM > LOW
- Provide concrete fix suggestions
"""


def _extract_verdict(text: str) -> tuple[ReviewVerdict, list[str]]:
    """Парсит вердикт и список замечаний из текста ревью."""
    lower = text.lower()

    if "✅" in text or "approved" in lower:
        verdict = ReviewVerdict.APPROVED
    elif "❌" in text or "rejected" in lower:
        verdict = ReviewVerdict.REJECTED
    elif "⚠️" in text or "needs_fix" in lower or "needs fix" in lower:
        verdict = ReviewVerdict.NEEDS_FIX
    else:
        verdict = ReviewVerdict.APPROVED  # fallback

    # Вытаскиваем список замечаний (строки с - / * / числами)
    comments: list[str] = []
    lines = text.split("\n")
    in_issues = False
    for line in lines:
        stripped = line.strip()
        if any(kw in stripped.lower() for kw in ["issue", "problem", "critical", "high", "medium", "must fix"]):
            in_issues = True
        if in_issues and re.match(r"^[\-\*\d\.\•]", stripped):
            clean = re.sub(r"^[\-\*\d\.\•\s]+", "", stripped).strip()
            if clean and len(clean) > 10:
                comments.append(clean)
    
    return verdict, comments[:20]  # макс 20 замечаний


def _build_reviewer_prompt(state: GibState) -> str:
    code = state.get("code_result", "")
    arch = state.get("architecture_result", "")
    research = state.get("research_result", "")
    iteration = state.get("review_iteration", 1)
    files = state.get("file_contents", {})

    parts = [
        f"## Task Being Reviewed\n{state.get('user_request', '')}",
    ]

    if arch:
        parts.append(f"\n## Architecture Design\n{arch[:2000]}")
    if code:
        parts.append(f"\n## Implementation to Review\n{code[:8000]}")
    if research:
        parts.append(f"\n## Research Context\n{research[:1500]}")

    if iteration > 1:
        parts.append(f"\n⚠️ This is iteration {iteration} — previous review found issues.")

    return "\n".join(p for p in parts if p)


async def node_reviewer(state: GibState) -> dict:
    """
    LangGraph Node: Claude проводит код-ревью.
    """
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = state.get("selected_models", {}).get(
        AgentRole.REVIEWER.value,
        router.select_model(TaskType.REVIEW)
    )
    prompt = _build_reviewer_prompt(state)
    iteration = state.get("review_iteration", 1)

    logger.info("[reviewer] Ревью итерация=%d, модель=%s", iteration, model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_REVIEWER_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.1,
        max_tokens=6144,
    )

    verdict, comments = _extract_verdict(resp.content)
    logger.info("[reviewer] Вердикт: %s (%d замечаний)", verdict.value, len(comments))

    output = AgentOutput(
        role=AgentRole.REVIEWER,
        model_id=resp.model,
        content=resp.content,
        cost_usd=resp.cost_usd,
        latency_ms=resp.latency_ms,
        metadata={"verdict": verdict.value, "comments_count": len(comments)},
    )

    return {
        "review_result": resp.content,
        "review_verdict": verdict.value,
        "review_comments": comments,
        "review_iteration": iteration + 1,
        "agent_outputs": [output],
        "completed_agents": [AgentRole.REVIEWER.value],
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "success": verdict in (ReviewVerdict.APPROVED, ReviewVerdict.NEEDS_FIX),
        "logs": [f"[Reviewer] {verdict.value}, {len(comments)} comments, model={resp.model}"],
    }


def route_after_review(state: GibState) -> str:
    """Conditional edge: маршрутизирует после ревью."""
    verdict = state.get("review_verdict", ReviewVerdict.APPROVED.value)
    iteration = state.get("review_iteration", 2)
    max_iter = state.get("max_review_iterations", 2)

    if verdict == ReviewVerdict.APPROVED.value:
        return "approved"

    if iteration > max_iter:
        logger.info("[reviewer] Итерации исчерпаны → принудительно завершаем")
        return "approved"  # завершаем даже если не идеально

    return "needs_fix"
