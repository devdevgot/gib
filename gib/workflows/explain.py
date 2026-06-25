"""Explain Workflow — объяснение кода/файлов.

Граф:
  analyzer → context_builder → researcher → END
  (researcher использует Gemini для объяснения)
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from gib.core.state import GibState
from gib.nodes.analyzer import node_project_analyzer
from gib.nodes.context_builder import node_context_builder
from gib.nodes.researcher import node_researcher
from gib.workflows.base import BaseWorkflow


async def _node_explainer(state: GibState) -> dict:
    """Специализированный explainer — передаёт задачу как запрос на объяснение."""
    # Модифицируем запрос для режима объяснения
    modified = {**state, "user_request": f"Explain this code in detail: {state.get('user_request', '')}"}
    return await node_researcher(modified)


class ExplainWorkflow(BaseWorkflow):
    """
    Explain Workflow: объясняет код используя Gemini.
    """

    @classmethod
    def build_graph(cls):
        g = StateGraph(GibState)

        g.add_node("analyzer", node_project_analyzer)
        g.add_node("context_builder", node_context_builder)
        g.add_node("explainer", _node_explainer)

        g.set_entry_point("analyzer")
        g.add_edge("analyzer", "context_builder")
        g.add_edge("context_builder", "explainer")
        g.add_edge("explainer", END)

        return g
