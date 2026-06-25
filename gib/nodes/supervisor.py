"""Node: Supervisor — управляет флоу выполнения.

Не пишет код. Только принимает решения: продолжать / повторить / завершить.
"""
from __future__ import annotations

from gib.core.state import GibState
from gib.core.types import ReviewVerdict, ApprovalStatus
from gib.utils import get_logger

logger = get_logger("gib.nodes.supervisor")


def node_supervisor(state: GibState) -> dict:
    """
    Синхронный Node (не требует LLM).
    
    Анализирует текущее состояние и принимает решение о следующем шаге.
    """
    completed = set(state.get("completed_agents", []))
    failed = set(state.get("failed_agents", []))
    verdict = state.get("review_verdict", ReviewVerdict.APPROVED.value)
    approval = state.get("approval_status", ApprovalStatus.PENDING.value)
    iteration = state.get("review_iteration", 1)
    max_iter = state.get("max_review_iterations", 2)

    logs: list[str] = []

    # Если пользователь отклонил — завершаем
    if approval == ApprovalStatus.REJECTED.value:
        decision = "abort"
        logs.append("[Supervisor] User rejected changes → abort")

    # Если ревью провалилось и итерации исчерпаны → завершаем как есть
    elif verdict in (ReviewVerdict.NEEDS_FIX.value, ReviewVerdict.REJECTED.value) \
            and iteration > max_iter:
        decision = "finish"
        logs.append(f"[Supervisor] Max iterations reached ({max_iter}) → finish")

    # Если ревью провалилось и есть итерации → повторяем агентов
    elif verdict in (ReviewVerdict.NEEDS_FIX.value, ReviewVerdict.REJECTED.value):
        decision = "retry"
        logs.append(f"[Supervisor] Review failed ({verdict}), iteration {iteration} → retry agents")

    # Если есть критические ошибки безопасности
    elif not state.get("security_passed", True):
        decision = "security_block"
        logs.append("[Supervisor] Security issues found → security_block")

    # Всё ок
    else:
        decision = "continue"
        logs.append("[Supervisor] All checks passed → continue")

    logger.info("[supervisor] Decision: %s (verdict=%s, iter=%d/%d)",
                decision, verdict, iteration, max_iter)

    return {
        "supervisor_decision": decision,
        "logs": logs,
    }


def route_supervisor(state: GibState) -> str:
    """Conditional edge — маршрутизирует по решению Supervisor."""
    decision = state.get("supervisor_decision", "continue")
    return {
        "continue": "continue",
        "retry": "retry",
        "abort": "abort",
        "finish": "finish",
        "security_block": "security_block",
    }.get(decision, "continue")
