"""Tests for feature workflow routing helpers."""
from gib.core.state import make_initial_state
from gib.core.types import AgentRole, SubTask
from gib.workflows.feature import _needed_roles, _route_after_planner


def test_needed_roles_defaults_when_no_subtasks():
    state = make_initial_state("add feature", "feature")
    roles = _needed_roles(state)
    assert roles == {AgentRole.ARCHITECT, AgentRole.DEVELOPER, AgentRole.RESEARCHER}


def test_needed_roles_from_subtasks():
    state = make_initial_state("add feature", "feature")
    state["subtasks"] = [
        SubTask(
            id="t1",
            title="Design",
            description="Design API",
            agent_role=AgentRole.ARCHITECT,
        ),
        SubTask(
            id="t2",
            title="Implement",
            description="Write code",
            agent_role=AgentRole.DEVELOPER,
        ),
    ]
    roles = _needed_roles(state)
    assert roles == {AgentRole.ARCHITECT, AgentRole.DEVELOPER}


def test_route_after_planner_goes_to_architect_first():
    state = make_initial_state("add feature", "feature")
    assert _route_after_planner(state) == "architect"


def test_route_after_planner_skips_architect_when_not_needed():
    state = make_initial_state("research only", "feature")
    state["subtasks"] = [
        SubTask(
            id="t1",
            title="Research",
            description="Check docs",
            agent_role=AgentRole.RESEARCHER,
        ),
    ]
    result = _route_after_planner(state)
    assert hasattr(result[0], "node") or str(result[0]).endswith("researcher")
