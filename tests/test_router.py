"""Tests for Model Router."""
import pytest
from gib.router import ModelRouter, TaskType


def test_detect_task_type_fix():
    router = ModelRouter()
    assert router.detect_task_type("fix the bug in auth") == TaskType.FIX


def test_detect_task_type_refactor():
    router = ModelRouter()
    assert router.detect_task_type("refactor this module") == TaskType.REFACTOR


def test_detect_task_type_test():
    router = ModelRouter()
    assert router.detect_task_type("write tests for auth.py") == TaskType.TEST


def test_detect_task_type_docs():
    router = ModelRouter()
    assert router.detect_task_type("document this code") == TaskType.DOCS


def test_detect_task_type_general():
    router = ModelRouter()
    assert router.detect_task_type("add a new feature") == TaskType.GENERAL


def test_select_model_returns_string():
    router = ModelRouter()
    model = router.select_model(TaskType.REVIEW)
    assert isinstance(model, str)
    assert "/" in model  # should be org/model format


def test_route_returns_tuple():
    router = ModelRouter()
    task_type, model = router.route("fix the error in main.py")
    assert task_type == TaskType.FIX
    assert isinstance(model, str)
