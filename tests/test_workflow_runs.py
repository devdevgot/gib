"""Tests for paused workflow run metadata."""
from gib.memory.store import MemoryStore


def test_workflow_run_pause_and_list(tmp_path):
    store = MemoryStore(db_path=tmp_path / "mem.db")
    project = str(tmp_path.resolve())

    store.create_workflow_run(
        thread_id="thread-abc",
        workflow_type="feature",
        user_request="add auth",
        project_path=project,
        task_type="general",
    )
    store.pause_workflow_run("thread-abc", "credits exhausted")

    paused = store.list_paused_runs(project)
    assert len(paused) == 1
    assert paused[0].thread_id == "thread-abc"
    assert paused[0].status == "paused_credits"

    latest = store.get_latest_paused_run(project)
    assert latest is not None
    assert latest.thread_id == "thread-abc"

    store.complete_workflow_run("thread-abc")
    assert store.list_paused_runs(project) == []
