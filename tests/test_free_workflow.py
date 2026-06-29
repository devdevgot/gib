"""Tests for free workflow (gibf)."""
from gib.core.types import AgentRole, ReviewVerdict, WorkflowType
from gib.graph.registry import WorkflowRegistry
from gib.workflows.free import FREE_MODELS, FreeWorkflow, _route_after_review_free


def test_free_models_use_agent_role_keys():
    assert FREE_MODELS[AgentRole.ARCHITECT.value] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert FREE_MODELS[AgentRole.DEVELOPER.value] == "cohere/north-mini-code:free"
    assert FREE_MODELS[AgentRole.REVIEWER.value] == "poolside/laguna-m.1:free"


def test_free_workflow_registered():
    assert WorkflowType.FREE.value in WorkflowRegistry.list()
    assert WorkflowRegistry.get(WorkflowType.FREE) is FreeWorkflow


def test_route_after_review_free_sends_to_fixer_on_first_needs_fix():
    state = {
        "review_verdict": ReviewVerdict.NEEDS_FIX.value,
        "review_iteration": 2,
    }
    assert _route_after_review_free(state) == "fixer_free"


def test_route_after_review_free_skips_fixer_after_limit():
    state = {
        "review_verdict": ReviewVerdict.NEEDS_FIX.value,
        "review_iteration": 3,
    }
    assert _route_after_review_free(state) == "patch_builder"


def test_route_after_review_free_approved_goes_to_patch():
    state = {
        "review_verdict": ReviewVerdict.APPROVED.value,
        "review_iteration": 2,
    }
    assert _route_after_review_free(state) == "patch_builder"


def test_free_workflow_graph_builds():
    graph = FreeWorkflow.build_graph()
    assert graph is not None
