"""Tests for memory context helpers."""
from gib.memory.context import build_project_memory_context, extract_task_summary, normalize_project_path
from gib.memory.store import MemoryStore


def test_normalize_project_path_resolves(tmp_path):
    sub = tmp_path / "proj"
    sub.mkdir()
    assert normalize_project_path(str(sub)) == str(sub.resolve())


def test_extract_task_summary_prefers_final_output():
    state = {
        "final_output": "final",
        "review_result": "review",
        "code_result": "code",
    }
    assert extract_task_summary(state) == "final"


def test_extract_task_summary_falls_back_to_research():
    state = {"research_result": "explanation text"}
    assert extract_task_summary(state) == "explanation text"


def test_build_project_memory_context_includes_tasks_without_summary(tmp_path):
    store = MemoryStore(db_path=tmp_path / "mem.db")
    project = str(tmp_path.resolve())
    store.save_task(
        task_type="explain",
        prompt="explain auth",
        result_summary="",
        project_path=project,
    )
    store.save_task(
        task_type="review",
        prompt="review code",
        result_summary="found 2 issues",
        project_path=project,
    )
    ctx = build_project_memory_context(store, project, include_chat=False)
    assert "explain auth" in ctx
    assert "found 2 issues" in ctx
    assert "результат не сохранён" in ctx
