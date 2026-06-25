"""Feature Workflow — полный пайплайн для новых фич.

Граф:
  analyzer → context_builder → file_finder → task_planner
    → architect
    → [developer ‖ researcher]  (параллельно, с учётом subtasks)
    → merge → reviewer
    → security → test_generator → patch_builder → approval
    → (approved → git | rejected → END)
    → END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from gib.core.state import GibState
from gib.core.types import AgentRole
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

_DEFAULT_ROLES = {AgentRole.ARCHITECT, AgentRole.DEVELOPER, AgentRole.RESEARCHER}


def _needed_roles(state: GibState) -> set[AgentRole]:
    """Определяет какие агенты нужны по subtasks от планировщика."""
    subtasks = state.get("subtasks", [])
    if not subtasks:
        return set(_DEFAULT_ROLES)

    roles: set[AgentRole] = set()
    for st in subtasks:
        role = st.agent_role if isinstance(st.agent_role, AgentRole) else AgentRole(st.agent_role)
        if role in _DEFAULT_ROLES:
            roles.add(role)
    return roles or set(_DEFAULT_ROLES)


def _parallel_post_architect_router(state: GibState):
    """
    Fan-out после architect: developer и/или researcher параллельно.
    Architect уже записал architecture_result — downstream агенты его видят.
    """
    roles = _needed_roles(state)
    sends: list[Send] = []
    if AgentRole.DEVELOPER in roles:
        sends.append(Send("developer", state))
    if AgentRole.RESEARCHER in roles:
        sends.append(Send("researcher", state))
    if sends:
        return sends
    return "merge"


def _route_after_planner(state: GibState):
    """После планировщика: architect первым, или сразу к dev/research."""
    roles = _needed_roles(state)
    if AgentRole.ARCHITECT in roles:
        return "architect"
    return _parallel_post_architect_router(state)


class FeatureWorkflow(BaseWorkflow):
    """
    Feature Workflow: полный пайплайн разработки новой функциональности.

    Архитектура:
    - file_finder: семантический поиск релевантных файлов
    - Последовательный architect, затем параллельные developer + researcher
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

        # ── Агенты (architect → parallel dev/research) ───────────────────────
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

        # Планировщик → architect (или прямо к dev/research если architect не нужен)
        g.add_conditional_edges(
            "task_planner",
            _route_after_planner,
            ["architect", "developer", "researcher", "merge"],
        )

        # Architect → parallel developer + researcher (или merge)
        g.add_conditional_edges(
            "architect",
            _parallel_post_architect_router,
            ["developer", "researcher", "merge"],
        )

        # Fan-in после параллельных агентов
        g.add_edge("developer", "merge")
        g.add_edge("researcher", "merge")

        g.add_edge("merge", "reviewer")

        # Условный переход после ревью
        g.add_conditional_edges(
            "reviewer",
            route_after_review,
            {
                "approved": "security",
                "needs_fix": "developer",
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
