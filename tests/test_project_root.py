"""Tests for project root resolution."""
from pathlib import Path

from gib.core.state import make_initial_state
from gib.utils.project_root import get_project_root


def test_get_project_root_from_explicit_field():
    state = make_initial_state("task", "feature", project_root="/tmp/myproject")
    assert get_project_root(state) == Path("/tmp/myproject")


def test_get_project_root_from_project_context():
    state = {"project_context": {"root": "/tmp/from-context"}}
    assert get_project_root(state) == Path("/tmp/from-context")
