"""LangGraph графы для GIB пайплайнов."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from gib.pipeline.state import PipelineState
from gib.pipeline.nodes import (
    node_architect,
    node_developer,
    node_reviewer,
    node_fix_developer,
    node_fix_reviewer,
    route_after_review,
    route_after_fix_review,
)


def build_general_graph() -> StateGraph:
    """
    Граф для gib ask / gib refactor:
    
    architect → developer → reviewer ─── approved ──→ END
                    ↑                └── needs_fix ──→ developer (retry, max 2)
                    └──────────────────────────────────┘
    """
    g = StateGraph(PipelineState)

    g.add_node("architect", node_architect)
    g.add_node("developer", node_developer)
    g.add_node("reviewer", node_reviewer)

    g.set_entry_point("architect")
    g.add_edge("architect", "developer")
    g.add_edge("developer", "reviewer")

    g.add_conditional_edges(
        "reviewer",
        route_after_review,
        {
            "end": END,
            "retry_developer": "developer",
        },
    )

    return g.compile()


def build_fix_graph() -> StateGraph:
    """
    Граф для gib fix (без архитектора):

    fix_developer → fix_reviewer ─── approved ──→ END
          ↑                      └── needs_fix ──→ fix_developer (retry, max 2)
          └─────────────────────────────────────────┘
    """
    g = StateGraph(PipelineState)

    g.add_node("fix_developer", node_fix_developer)
    g.add_node("fix_reviewer", node_fix_reviewer)

    g.set_entry_point("fix_developer")
    g.add_edge("fix_developer", "fix_reviewer")

    g.add_conditional_edges(
        "fix_reviewer",
        route_after_fix_review,
        {
            "end": END,
            "retry_fix_developer": "fix_developer",
        },
    )

    return g.compile()


# Синглтоны — компилируем один раз
_general_graph = None
_fix_graph = None


def get_general_graph():
    global _general_graph
    if _general_graph is None:
        _general_graph = build_general_graph()
    return _general_graph


def get_fix_graph():
    global _fix_graph
    if _fix_graph is None:
        _fix_graph = build_fix_graph()
    return _fix_graph
