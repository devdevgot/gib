"""Free Workflow — бесплатный пайплайн на моделях OpenRouter free tier.

Граф:
  context_builder → file_finder
    → architect_free (nemotron-ultra)
    → developer_free (north-mini-code)
    → reviewer_free (laguna-m.1)
    → fixer_free (north-mini-code, если reviewer нашёл замечания)
    → qa_free (laguna-m.1, финальная проверка)
    → patch_builder → approval
    → (approved → git | skip → END)
    → END

Модели передаются через selected_models в GibState:
  architect  → nvidia/nemotron-3-ultra-550b-a55b:free
  developer  → cohere/north-mini-code:free
  reviewer   → poolside/laguna-m.1:free
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from gib.core.state import GibState
from gib.core.types import ReviewVerdict
from gib.nodes.context_builder import node_context_builder
from gib.nodes.file_finder import node_file_finder
from gib.nodes.architect import node_architect
from gib.nodes.developer import node_developer
from gib.nodes.reviewer import node_reviewer
from gib.nodes.patch_builder import node_patch_builder
from gib.nodes.approval import node_approval, route_after_approval
from gib.nodes.git_node import node_git
from gib.workflows.base import BaseWorkflow

# ── Модели (free tier) ───────────────────────────────────────────────────────
FREE_MODELS: dict[str, str] = {
    "architect": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "developer": "cohere/north-mini-code:free",
    "reviewer":  "poolside/laguna-m.1:free",
}

_MAX_REVIEW_ITERS = 1


def _route_after_review_free(state: GibState) -> str:
    """
    После reviewer_free:
    - первая итерация с замечаниями → fixer_free
    - одобрено или лимит → patch_builder
    """
    verdict = state.get("review_verdict", ReviewVerdict.APPROVED.value)
    iteration = state.get("review_iteration", 0)

    if verdict == ReviewVerdict.NEEDS_FIX.value and iteration <= _MAX_REVIEW_ITERS:
        return "fixer_free"
    return "patch_builder"


def _inject_free_models(state: GibState) -> GibState:
    """Начальный узел — подставляет free модели в selected_models."""
    return {"selected_models": FREE_MODELS}


class FreeWorkflow(BaseWorkflow):
    """
    Free Workflow — полный пайплайн без затрат.

    Pipeline:
      inject_models → context_builder → file_finder
        → architect_free → developer_free → reviewer_free
        → fixer_free (если есть замечания) → qa_free
        → patch_builder → approval → git → END
    """

    @classmethod
    def build_graph(cls):
        g = StateGraph(GibState)

        # ── Инъекция моделей ────────────────────────────────────────────────
        g.add_node("inject_models", _inject_free_models)

        # ── Подготовительные узлы ───────────────────────────────────────────
        g.add_node("context_builder", node_context_builder)
        g.add_node("file_finder", node_file_finder)

        # ── Агенты ──────────────────────────────────────────────────────────
        # Переиспользуем существующие ноды; модели берутся из selected_models
        g.add_node("architect_free",  node_architect)
        g.add_node("developer_free",  node_developer)
        g.add_node("reviewer_free",   node_reviewer)
        g.add_node("fixer_free",      node_developer)   # повторный developer
        g.add_node("qa_free",         node_reviewer)    # финальный reviewer

        # ── Патч, одобрение, git ────────────────────────────────────────────
        g.add_node("patch_builder", node_patch_builder)
        g.add_node("approval",      node_approval)
        g.add_node("git",           node_git)

        # ── Рёбра ───────────────────────────────────────────────────────────
        g.set_entry_point("inject_models")
        g.add_edge("inject_models",   "context_builder")
        g.add_edge("context_builder", "file_finder")
        g.add_edge("file_finder",     "architect_free")
        g.add_edge("architect_free",  "developer_free")
        g.add_edge("developer_free",  "reviewer_free")

        g.add_conditional_edges(
            "reviewer_free",
            _route_after_review_free,
            {
                "fixer_free":    "fixer_free",
                "patch_builder": "patch_builder",
            },
        )

        g.add_edge("fixer_free",  "qa_free")
        g.add_edge("qa_free",     "patch_builder")
        g.add_edge("patch_builder", "approval")

        g.add_conditional_edges(
            "approval",
            route_after_approval,
            {
                "apply": "git",
                "skip":  END,
            },
        )

        g.add_edge("git", END)

        return g  # compile() вызывается в BaseWorkflow.run() с checkpointer
