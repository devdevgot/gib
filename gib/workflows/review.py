"""Review Workflow — только код-ревью без изменений.

Граф:
  analyzer → context_builder → reviewer → security → END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from gib.core.state import GibState
from gib.nodes.analyzer import node_project_analyzer
from gib.nodes.context_builder import node_context_builder
from gib.nodes.reviewer import node_reviewer
from gib.nodes.security import node_security
from gib.workflows.base import BaseWorkflow


class ReviewWorkflow(BaseWorkflow):
    """
    Review Workflow: только аналитика, никаких изменений.
    
    reviewer выносит вердикт + security scan → отчёт пользователю.
    """

    @classmethod
    def build_graph(cls):
        g = StateGraph(GibState)

        g.add_node("analyzer", node_project_analyzer)
        g.add_node("context_builder", node_context_builder)
        g.add_node("reviewer", node_reviewer)
        g.add_node("security", node_security)

        g.set_entry_point("analyzer")
        g.add_edge("analyzer", "context_builder")
        g.add_edge("context_builder", "reviewer")
        g.add_edge("reviewer", "security")
        g.add_edge("security", END)

        return g.compile()
