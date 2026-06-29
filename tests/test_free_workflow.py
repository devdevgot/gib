"""Tests for free workflow (gibf)."""
from gib.core.types import AgentRole, ReviewVerdict, WorkflowType
from gib.graph.registry import WorkflowRegistry
from gib.workflows.free import FreeWorkflow, _route_after_qa_free, _route_after_review_free, _route_scope
from gib.workflows.free_config import FREE_MODELS, is_simple_free_task


def test_free_models_include_finder_and_security():
    assert FREE_MODELS[AgentRole.ARCHITECT.value] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert FREE_MODELS[AgentRole.DEVELOPER.value] == "cohere/north-mini-code:free"
    assert FREE_MODELS[AgentRole.REVIEWER.value] == "poolside/laguna-m.1:free"
    assert FREE_MODELS["file_finder"] == "nvidia/nemotron-3-super-120b-a12b:free"
    assert FREE_MODELS["security"] == "nvidia/nemotron-3-ultra-550b-a55b:free"


def test_free_workflow_registered():
    assert WorkflowType.FREE.value in WorkflowRegistry.list()
    assert WorkflowRegistry.get(WorkflowType.FREE) is FreeWorkflow


def test_is_simple_free_task():
    assert is_simple_free_task("исправь опечатку в README")
    assert is_simple_free_task("fix typo")
    assert not is_simple_free_task(
        "спроектируй и реализуй полноценную систему аутентификации с OAuth2 и refresh tokens"
    )


def test_route_scope_simple_goes_to_developer():
    state = {"user_request": "исправь опечатку в README"}
    assert _route_scope(state) == "developer_free"


def test_route_scope_complex_goes_to_architect():
    state = {"user_request": "спроектируй микросервисную архитектуру billing модуля"}
    assert _route_scope(state) == "architect_free"


def test_route_after_review_free_sends_to_fixer_on_first_needs_fix():
    state = {
        "review_verdict": ReviewVerdict.NEEDS_FIX.value,
        "review_iteration": 2,
    }
    assert _route_after_review_free(state) == "fixer_free"


def test_route_after_review_free_approved_goes_to_security():
    state = {
        "review_verdict": ReviewVerdict.APPROVED.value,
        "review_iteration": 2,
    }
    assert _route_after_review_free(state) == "security"


def test_route_after_qa_free_retries_fixer():
    state = {
        "review_verdict": ReviewVerdict.NEEDS_FIX.value,
        "review_iteration": 3,
    }
    assert _route_after_qa_free(state) == "fixer_free"


def test_route_after_qa_free_exhausted_goes_to_security():
    state = {
        "review_verdict": ReviewVerdict.NEEDS_FIX.value,
        "review_iteration": 4,
    }
    assert _route_after_qa_free(state) == "security"


def test_free_workflow_graph_builds():
    graph = FreeWorkflow.build_graph()
    assert graph is not None
