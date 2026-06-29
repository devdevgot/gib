"""Free Workflow — бесплатный пайплайн на моделях OpenRouter free tier.

Граф:
  inject_models → analyzer → context_builder → file_finder → scope_router
    → [simple] developer_free → security
    → [complex] architect_free → developer_free → reviewer_free
        → fixer_free (если замечания) → qa_free → security
    → patch_builder → approval → git → END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from gib.core.state import GibState
from gib.core.types import ReviewVerdict
from gib.nodes.analyzer import node_project_analyzer
from gib.nodes.context_builder import node_context_builder
from gib.nodes.file_finder import node_file_finder
from gib.nodes.architect import node_architect
from gib.nodes.developer import node_developer
from gib.nodes.reviewer import node_reviewer
from gib.nodes.security import node_security
from gib.nodes.patch_builder import node_patch_builder
from gib.nodes.approval import node_approval, route_after_approval
from gib.nodes.git_node import node_git
from gib.workflows.base import BaseWorkflow
from gib.workflows.free_config import (
    FREE_METADATA,
    FREE_MODELS,
    MAX_REVIEW_ITERS,
    is_simple_free_task,
)

# Re-export for backward compatibility
__all__ = ["FREE_MODELS", "FreeWorkflow"]


def _route_after_review_free(state: GibState) -> str:
    """После reviewer_free: fixer или security."""
    verdict = state.get("review_verdict", ReviewVerdict.APPROVED.value)
    iteration = state.get("review_iteration", 1)

    if verdict == ReviewVerdict.NEEDS_FIX.value and iteration <= MAX_REVIEW_ITERS + 1:
        return "fixer_free"
    return "security"


def _route_after_qa_free(state: GibState) -> str:
    """После qa_free: повторный fixer или security."""
    verdict = state.get("review_verdict", ReviewVerdict.APPROVED.value)
    iteration = state.get("review_iteration", 1)

    if verdict == ReviewVerdict.NEEDS_FIX.value and iteration <= MAX_REVIEW_ITERS + 2:
        return "fixer_free"
    return "security"


def _route_scope(state: GibState) -> str:
    """Простые задачи — сразу к разработчику, сложные — через архитектора."""
    if is_simple_free_task(state.get("user_request", "")):
        return "developer_free"
    return "architect_free"


def _inject_free_models(state: GibState) -> dict:
    """Начальный узел — free модели и лимиты контекста."""
    meta = dict(state.get("metadata", {}))
    meta.update(FREE_METADATA)
    return {"selected_models": FREE_MODELS, "metadata": meta}


class FreeWorkflow(BaseWorkflow):
    """Free Workflow — полный пайплайн без затрат на платных моделях."""

    @classmethod
    def build_graph(cls):
        g = StateGraph(GibState)

        g.add_node("inject_models", _inject_free_models)
        g.add_node("analyzer", node_project_analyzer)
        g.add_node("context_builder", node_context_builder)
        g.add_node("file_finder", node_file_finder)

        g.add_node("architect_free", node_architect)
        g.add_node("developer_free", node_developer)
        g.add_node("reviewer_free", node_reviewer)
        g.add_node("fixer_free", node_developer)
        g.add_node("qa_free", node_reviewer)
        g.add_node("security", node_security)

        g.add_node("patch_builder", node_patch_builder)
        g.add_node("approval", node_approval)
        g.add_node("git", node_git)

        g.set_entry_point("inject_models")
        g.add_edge("inject_models", "analyzer")
        g.add_edge("analyzer", "context_builder")
        g.add_edge("context_builder", "file_finder")

        g.add_conditional_edges(
            "file_finder",
            _route_scope,
            {
                "architect_free": "architect_free",
                "developer_free": "developer_free",
            },
        )

        g.add_edge("architect_free", "developer_free")

        g.add_conditional_edges(
            "developer_free",
            lambda state: (
                "security"
                if is_simple_free_task(state.get("user_request", ""))
                else "reviewer_free"
            ),
            {
                "reviewer_free": "reviewer_free",
                "security": "security",
            },
        )

        g.add_conditional_edges(
            "reviewer_free",
            _route_after_review_free,
            {
                "fixer_free": "fixer_free",
                "security": "security",
            },
        )

        g.add_edge("fixer_free", "qa_free")

        g.add_conditional_edges(
            "qa_free",
            _route_after_qa_free,
            {
                "fixer_free": "fixer_free",
                "security": "security",
            },
        )

        g.add_edge("security", "patch_builder")
        g.add_edge("patch_builder", "approval")

        g.add_conditional_edges(
            "approval",
            route_after_approval,
            {
                "apply": "git",
                "skip": END,
            },
        )

        g.add_edge("git", END)

        return g
