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


def _format_chunk(chunk: dict[str, str]) -> str:
    """Форматирует батч файлов для LLM."""
    parts = []
    for path, content in chunk.items():
        parts.append(f"### {path}\n```\n{content}\n```")
    return "\n\n".join(parts)


def _build_chunk_prompt(chunk: dict[str, str], chunk_idx: int, total: int, context: str) -> str:
    header = f"## Code Review — Batch {chunk_idx}/{total}\n"
    if context:
        header += f"\nProject context:\n{context[:500]}\n"
    header += f"\nReview these files ({len(chunk)} files):\n\n"
    return header + _format_chunk(chunk)


def _build_merge_prompt(partial_reviews: list[str], project_context: str) -> str:
    parts = [
        "## Merge Partial Code Reviews into One Final Report\n",
        f"Project: {project_context[:300]}\n",
        f"Total batches reviewed: {len(partial_reviews)}\n\n",
    ]
    for i, review in enumerate(partial_reviews, 1):
        parts.append(f"### Batch {i} Review\n{review}\n")
    parts.append(
        "\n## Your Task\n"
        "Consolidate all findings into ONE final report:\n"
        "1. Start with overall verdict: ✅ APPROVED / ⚠️ NEEDS_FIX / ❌ REJECTED\n"
        "2. Deduplicate — merge similar issues from different batches\n"
        "3. Prioritize: CRITICAL > HIGH > MEDIUM > LOW\n"
        "4. Include file references for each issue\n"
        "5. End with a summary of the most important fixes needed\n"
    )
    return "\n".join(parts)


def _build_reviewer_prompt(state: GibState) -> str:
    """Для не-review workflow (inline review после генерации кода)."""
    code = state.get("code_result", "")
    arch = state.get("architecture_result", "")
    research = state.get("research_result", "")
    iteration = state.get("review_iteration", 1)
    files = state.get("file_contents", {})

    parts = [f"## Task Being Reviewed\n{state.get('user_request', '')}"]

    if arch:
        parts.append(f"\n## Architecture Design\n{arch[:2000]}")
    if code:
        parts.append(f"\n## Implementation to Review\n{code[:8000]}")
    elif files:
        # Нет code_result — используем file_contents
        files_text = _format_chunk(dict(list(files.items())[:10]))
        parts.append(f"\n## Files to Review\n{files_text}")
    if research:
        parts.append(f"\n## Research Context\n{research[:1500]}")
    if iteration > 1:
        parts.append(f"\n⚠️ This is iteration {iteration} — previous review found issues.")

    return "\n".join(p for p in parts if p)


async def node_reviewer(state: GibState) -> dict:
    """
    LangGraph Node: Claude проводит код-ревью.

    Если в metadata есть review_chunks (review/doctor workflow) —
    анализирует каждый батч отдельно, затем мержит в финальный отчёт.
    Иначе — стандартный inline review после генерации кода.
    """
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = state.get("selected_models", {}).get(
        AgentRole.REVIEWER.value,
        router.select_model(TaskType.REVIEW)
    )
    iteration = state.get("review_iteration", 1)

    # Проверяем наличие батчей для chunked review
    metadata = state.get("metadata", {})
    chunks: list[dict[str, str]] = metadata.get("review_chunks", [])

    total_cost = 0.0
    total_latency = 0
    models_used: list[str] = []

    if chunks and len(chunks) > 1:
        # ── Chunked review: анализируем батч за батчем ──────────────────────
        project_info = (
            f"Language: {state.get('project_context', {}).get('language', 'Unknown')}\n"
            f"Frameworks: {state.get('project_context', {}).get('frameworks', [])}\n"
            f"Request: {state.get('user_request', '')}"
        )
        logger.info("[reviewer] Chunked review: %d батчей, модель=%s", len(chunks), model)

        partial_reviews: list[str] = []
        for idx, chunk in enumerate(chunks, 1):
            if not chunk:
                continue
            chunk_prompt = _build_chunk_prompt(chunk, idx, len(chunks), project_info)
            logger.info("[reviewer] Батч %d/%d (%d файлов)...", idx, len(chunks), len(chunk))

            resp = await client.chat(
                [
                    ChatMessage(role="system", content=_REVIEWER_SYSTEM),
                    ChatMessage(role="user", content=chunk_prompt),
                ],
                model=model,
                temperature=0.1,
                max_tokens=4096,
            )
            partial_reviews.append(resp.content)
            total_cost += resp.cost_usd
            total_latency += resp.latency_ms
            models_used.append(resp.model)

        # Мержим в финальный отчёт
        logger.info("[reviewer] Мержу %d частичных ревью...", len(partial_reviews))
        if len(partial_reviews) == 1:
            final_review = partial_reviews[0]
            merge_resp_model = models_used[0]
        else:
            merge_prompt = _build_merge_prompt(partial_reviews, project_info)
            merge_resp = await client.chat(
                [
                    ChatMessage(role="system", content=_REVIEWER_SYSTEM),
                    ChatMessage(role="user", content=merge_prompt),
                ],
                model=model,
                temperature=0.1,
                max_tokens=6144,
            )
            final_review = merge_resp.content
            total_cost += merge_resp.cost_usd
            total_latency += merge_resp.latency_ms
            models_used.append(merge_resp.model)
            merge_resp_model = merge_resp.model

        review_text = final_review
        used_model = merge_resp_model if len(partial_reviews) > 1 else models_used[0]

    else:
        # ── Стандартный inline review (один батч или нет батчей) ────────────
        # Если один батч — используем его файлы напрямую
        if chunks and len(chunks) == 1:
            project_info = (
                f"Language: {state.get('project_context', {}).get('language', 'Unknown')}\n"
                f"Request: {state.get('user_request', '')}"
            )
            prompt = _build_chunk_prompt(chunks[0], 1, 1, project_info)
        else:
            prompt = _build_reviewer_prompt(state)

        logger.info("[reviewer] Inline review, итерация=%d, модель=%s", iteration, model)

        resp = await client.chat(
            [
                ChatMessage(role="system", content=_REVIEWER_SYSTEM),
                ChatMessage(role="user", content=prompt),
            ],
            model=model,
            temperature=0.1,
            max_tokens=6144,
        )
        review_text = resp.content
        total_cost = resp.cost_usd
        total_latency = resp.latency_ms
        models_used = [resp.model]
        used_model = resp.model

    verdict, comments = _extract_verdict(review_text)
    logger.info("[reviewer] Вердикт: %s (%d замечаний)", verdict.value, len(comments))

    output = AgentOutput(
        role=AgentRole.REVIEWER,
        model_id=used_model,
        content=review_text,
        cost_usd=total_cost,
        latency_ms=total_latency,
        metadata={
            "verdict": verdict.value,
            "comments_count": len(comments),
            "chunks_processed": len(chunks) if chunks else 1,
        },
    )

    return {
        "review_result": review_text,
        "review_verdict": verdict.value,
        "review_comments": comments,
        "review_iteration": iteration + 1,
        "agent_outputs": [output],
        "completed_agents": [AgentRole.REVIEWER.value],
        "total_cost_usd": total_cost,
        "total_latency_ms": total_latency,
        "models_used": models_used,
        "success": verdict in (ReviewVerdict.APPROVED, ReviewVerdict.NEEDS_FIX),
        "logs": [
            f"[Reviewer] {verdict.value}, {len(comments)} issues, "
            f"{len(chunks) if chunks else 1} chunk(s), model={used_model}"
        ],
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
