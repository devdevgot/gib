"""Refactor Workflow — рефакторинг кода.

Граф:
  analyzer → context_builder → architect (план рефакторинга)
    → developer (применяет план)
    → reviewer → (needs_fix → developer | approved)
    → security → patch_builder → approval → git → END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from gib.core.state import GibState
from gib.nodes.analyzer import node_project_analyzer
from gib.nodes.context_builder import node_context_builder
from gib.nodes.architect import node_architect
from gib.nodes.developer import node_developer
from gib.nodes.reviewer import node_reviewer, route_after_review
from gib.nodes.security import node_security
from gib.nodes.patch_builder import node_patch_builder
from gib.nodes.approval import node_approval, route_after_approval
from gib.nodes.git_node import node_git
from gib.workflows.base import BaseWorkflow


class RefactorWorkflow(BaseWorkflow):
    """
    Refactor Workflow: architect создаёт план, developer применяет.
    
    architect → developer → reviewer → retry → security → patch → git
    """

    @classmethod
    def build_graph(cls):
        g = StateGraph(GibState)

        g.add_node("analyzer", node_project_analyzer)
        g.add_node("context_builder", node_context_builder)
        g.add_node("architect", node_architect)
        g.add_node("developer", node_developer)
        g.add_node("reviewer", node_reviewer)
        g.add_node("security", node_security)
        g.add_node("patch_builder", node_patch_builder)
        g.add_node("approval", node_approval)
        g.add_node("git", node_git)

        g.set_entry_point("analyzer")
        g.add_edge("analyzer", "context_builder")
        g.add_edge("context_builder", "architect")
        g.add_edge("architect", "developer")
        g.add_edge("developer", "reviewer")

        g.add_conditional_edges(
            "reviewer",
            route_after_review,
            {
                "approved": "security",
                "needs_fix": "developer",
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

        return g.compile()
