"""Feature Workflow — полный пайплайн для новых фич.

Граф:
  analyzer → context_builder → file_finder → task_planner
    → [architect ‖ developer ‖ researcher]  (параллельно)
    → merge → reviewer
    → supervisor → (needs_fix → developer | approved)
    → security → test_generator → patch_builder → approval
    → (approved → git | rejected → END)
    → END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from gib.core.state import GibState
from gib.core.types import ReviewVerdict
from gib.nodes.analyzer import node_project_analyzer
from gib.nodes.context_builder import node_context_builder
from gib.nodes.file_finder import node_file_finder
from gib.nodes.task_planner import node_task_planner
from gib.nodes.architect import node_architect
from gib.nodes.developer import node_developer
from gib.nodes.researcher import node_researcher
from gib.nodes.merge import node_merge
from gib.nodes.reviewer import node_reviewer, route_after_review
from gib.nodes.security import node_security
from gib.nodes.test_generator import node_test_generator
from gib.nodes.patch_builder import node_patch_builder
from gib.nodes.approval import node_approval, route_after_approval
from gib.nodes.git_node import node_git
from gib.workflows.base import BaseWorkflow


def _parallel_agents_router(state: GibState):
    """
    Fan-out: запускает architect, developer, researcher параллельно.
    LangGraph исполняет все Send() конкурентно через asyncio.
    """
    return [
        Send("architect", state),
        Send("developer", state),
        Send("researcher", state),
    ]


class FeatureWorkflow(BaseWorkflow):
    """
    Feature Workflow: полный пайплайн разработки новой функциональности.

    Архитектура:
    - file_finder: семантический поиск релевантных файлов
    - Параллельные агенты (architect + developer + researcher)
    - Автоматическое ревью с retry (макс 2 итерации)
    - Статический security scan
    - Генерация тестов
    - Human approval перед применением
    - Git интеграция
    """

    @classmethod
    def build_graph(cls):
        g = StateGraph(GibState)

        # ── Подготовительные узлы ────────────────────────────────────────────
        g.add_node("analyzer", node_project_analyzer)
        g.add_node("context_builder", node_context_builder)
        g.add_node("file_finder", node_file_finder)
        g.add_node("task_planner", node_task_planner)

        # ── Параллельные агенты ──────────────────────────────────────────────
        g.add_node("architect", node_architect)
        g.add_node("developer", node_developer)
        g.add_node("researcher", node_researcher)

        # ── Merge + Review ───────────────────────────────────────────────────
        g.add_node("merge", node_merge)
        g.add_node("reviewer", node_reviewer)

        # ── Безопасность, тесты, патч ────────────────────────────────────────
        g.add_node("security", node_security)
        g.add_node("test_generator", node_test_generator)
        g.add_node("patch_builder", node_patch_builder)

        # ── Одобрение и Git ──────────────────────────────────────────────────
        g.add_node("approval", node_approval)
        g.add_node("git", node_git)

        # ── Последовательные рёбра ───────────────────────────────────────────
        g.set_entry_point("analyzer")
        g.add_edge("analyzer", "context_builder")
        g.add_edge("context_builder", "file_finder")
        g.add_edge("file_finder", "task_planner")

        # Fan-out на параллельные агенты
        g.add_conditional_edges(
            "task_planner", _parallel_agents_router,
            ["architect", "developer", "researcher"],
        )

        # Fan-in после параллельных агентов
        g.add_edge("architect", "merge")
        g.add_edge("developer", "merge")
        g.add_edge("researcher", "merge")

        g.add_edge("merge", "reviewer")

        # Условный переход после ревью
        g.add_conditional_edges(
            "reviewer",
            route_after_review,
            {
                "approved": "security",
                "needs_fix": "developer",  # retry developer с замечаниями
            },
        )

        # После security → тесты → патч → одобрение
        g.add_edge("security", "test_generator")
        g.add_edge("test_generator", "patch_builder")
        g.add_edge("patch_builder", "approval")

        # После одобрения → git или конец
        g.add_conditional_edges(
            "approval",
            route_after_approval,
            {
                "apply": "git",
                "skip": END,
            },
        )

        g.add_edge("git", END)

        return g.compile()
