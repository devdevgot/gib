"""LangGraph nodes — каждый узел вызывает одну модель и обновляет состояние."""
from __future__ import annotations

import re
from typing import Any

from gib.pipeline.state import PipelineState
from gib.prompts.templates import PromptLibrary
from gib.providers import ChatMessage, OpenRouterClient
from gib.router import ModelRouter, TaskType
from gib.utils import get_logger
from gib.workspace.analyzer import ProjectProfile

logger = get_logger("gib.pipeline")

_router = ModelRouter()
_client = OpenRouterClient()


def _deserialize_profile(meta: dict[str, Any]) -> ProjectProfile | None:
    try:
        return ProjectProfile(**meta) if meta else None
    except Exception:
        return None


def _extract_verdict(review_text: str) -> str:
    """
    Парсит вердикт из текста ревью Gemini.
    Ищет '✅ Готово' / '⚠️ Требует правок' / '❌ Серьёзные проблемы'.
    """
    text = review_text.lower()
    if "✅" in review_text or "готово к использованию" in text or "код принят" in text:
        return "approved"
    if "❌" in review_text or "серьёзные проблемы" in text:
        return "rejected"
    if "⚠️" in review_text or "требует правок" in text:
        return "needs_fix"
    # fallback — если ничего не нашли, считаем approved
    return "approved"


# ──────────────────────────────────────────────────────────────
# Узел 1: Архитектор (Claude Opus 4.8)
# ──────────────────────────────────────────────────────────────

async def node_architect(state: PipelineState) -> dict:
    """Claude анализирует задачу и составляет план."""
    logger.info("[pipeline] Шаг: архитектор (Claude)")
    profile = _deserialize_profile(state.get("project_meta", {}))
    model = _router.select_model(TaskType.ARCHITECTURE)

    msgs = PromptLibrary.pipeline_architect(
        state["prompt"],
        state.get("file_context", ""),
        profile,
    )
    resp = await _client.chat(
        [ChatMessage(**m) for m in msgs],
        model=model,
        temperature=0.3,
        max_tokens=4096,
    )

    return {
        "architect_plan": resp.content,
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
    }


# ──────────────────────────────────────────────────────────────
# Узел 2: Разработчик (GPT-5.5)
# ──────────────────────────────────────────────────────────────

async def node_developer(state: PipelineState) -> dict:
    """GPT-5.5 пишет код по плану архитектора."""
    logger.info("[pipeline] Шаг: разработчик (GPT-5.5), итерация %d", state.get("iteration", 1))
    profile = _deserialize_profile(state.get("project_meta", {}))
    model = _router.select_model(TaskType.FIX)  # GPT-5.5

    # На повторной итерации — передаём предыдущий ревью как дополнительный контекст
    prompt = state["prompt"]
    if state.get("iteration", 1) > 1 and state.get("review_result"):
        prompt = (
            f"{prompt}\n\n"
            f"## Предыдущая попытка была отклонена ревьюером\n"
            f"Замечания ревьюера:\n{state['review_result']}\n\n"
            f"Исправь все замечания."
        )

    msgs = PromptLibrary.pipeline_developer(
        prompt,
        state.get("architect_plan", ""),
        state.get("file_context", ""),
        profile,
    )
    resp = await _client.chat(
        [ChatMessage(**m) for m in msgs],
        model=model,
        temperature=0.2,
        max_tokens=8192,
    )

    return {
        "developer_code": resp.content,
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
    }


# ──────────────────────────────────────────────────────────────
# Узел 3: Ревьюер (Gemini 2.5 Pro)
# ──────────────────────────────────────────────────────────────

async def node_reviewer(state: PipelineState) -> dict:
    """Gemini проверяет код и выносит вердикт."""
    logger.info("[pipeline] Шаг: ревьюер (Gemini), итерация %d", state.get("iteration", 1))
    profile = _deserialize_profile(state.get("project_meta", {}))
    model = _router.select_model(TaskType.REVIEW)  # Gemini 2.5 Pro

    msgs = PromptLibrary.pipeline_reviewer(
        state["prompt"],
        state.get("architect_plan", ""),
        state.get("developer_code", ""),
        profile,
    )
    resp = await _client.chat(
        [ChatMessage(**m) for m in msgs],
        model=model,
        temperature=0.1,
        max_tokens=8192,
    )

    verdict = _extract_verdict(resp.content)
    logger.info("[pipeline] Вердикт ревьюера: %s", verdict)

    return {
        "review_result": resp.content,
        "review_verdict": verdict,
        "final_output": resp.content,
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "success": verdict in ("approved", "needs_fix"),
        "iteration": state.get("iteration", 1) + 1,
    }


# ──────────────────────────────────────────────────────────────
# Узел 2b: Разработчик для fix-пайплайна (без архитектора)
# ──────────────────────────────────────────────────────────────

async def node_fix_developer(state: PipelineState) -> dict:
    """GPT-5.5 исправляет баг (для gib fix — без шага архитектора)."""
    logger.info("[pipeline] Шаг: fix-разработчик (GPT-5.5), итерация %d", state.get("iteration", 1))
    profile = _deserialize_profile(state.get("project_meta", {}))
    model = _router.select_model(TaskType.FIX)

    error = state.get("error_context", "")
    code = state.get("file_context", "")

    # На повторной итерации добавляем замечания ревьюера
    if state.get("iteration", 1) > 1 and state.get("review_result"):
        error = f"{error}\n\nЗамечания ревьюера:\n{state['review_result']}"

    msgs = PromptLibrary.fix(code, error=error, project=profile)
    resp = await _client.chat(
        [ChatMessage(**m) for m in msgs],
        model=model,
        temperature=0.1,
        max_tokens=8192,
    )

    return {
        "developer_code": resp.content,
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
    }


# ──────────────────────────────────────────────────────────────
# Узел 3b: Ревьюер для fix-пайплайна
# ──────────────────────────────────────────────────────────────

async def node_fix_reviewer(state: PipelineState) -> dict:
    """Gemini проверяет исправление бага."""
    logger.info("[pipeline] Шаг: fix-ревьюер (Gemini), итерация %d", state.get("iteration", 1))
    profile = _deserialize_profile(state.get("project_meta", {}))
    model = _router.select_model(TaskType.REVIEW)

    msgs = PromptLibrary.pipeline_fix_reviewer(
        state.get("file_context", ""),
        state.get("developer_code", ""),
        state.get("error_context", ""),
        profile,
    )
    resp = await _client.chat(
        [ChatMessage(**m) for m in msgs],
        model=model,
        temperature=0.1,
        max_tokens=4096,
    )

    verdict = _extract_verdict(resp.content)
    logger.info("[pipeline] Fix-вердикт ревьюера: %s", verdict)

    return {
        "review_result": resp.content,
        "review_verdict": verdict,
        "final_output": resp.content,
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "success": verdict in ("approved", "needs_fix"),
        "iteration": state.get("iteration", 1) + 1,
    }


# ──────────────────────────────────────────────────────────────
# Conditional edge — решает что делать после ревью
# ──────────────────────────────────────────────────────────────

def route_after_review(state: PipelineState) -> str:
    """
    Вердикт Gemini управляет флоу:
    - approved   → END
    - needs_fix  → developer (повторная итерация, макс 2)
    - rejected   → developer (повторная итерация, макс 2)
    - итерации исчерпаны → END
    """
    verdict = state.get("review_verdict", "approved")
    iteration = state.get("iteration", 2)
    max_iter = state.get("max_iterations", 2)

    if verdict == "approved":
        return "end"
    if iteration > max_iter:
        logger.info("[pipeline] Исчерпаны итерации (%d), завершаем", max_iter)
        return "end"
    return "retry_developer"


def route_after_fix_review(state: PipelineState) -> str:
    """То же, но для fix-пайплайна."""
    verdict = state.get("review_verdict", "approved")
    iteration = state.get("iteration", 2)
    max_iter = state.get("max_iterations", 2)

    if verdict == "approved":
        return "end"
    if iteration > max_iter:
        return "end"
    return "retry_fix_developer"
