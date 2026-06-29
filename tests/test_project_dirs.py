"""Tests for per-project .gib data directories."""
from pathlib import Path

from gib.utils.project_dirs import (
    checkpoint_db_path,
    cleanup_legacy_global_databases,
    ensure_gitignore,
    log_dir_path,
    memory_db_path,
    project_data_dir,
)


def test_project_data_dir_isolated_per_project(tmp_path):
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()

    dir_a = project_data_dir(project_a)
    dir_b = project_data_dir(project_b)

    assert dir_a == project_a / ".gib"
    assert dir_b == project_b / ".gib"
    assert dir_a != dir_b
    assert dir_a.is_dir()
    assert dir_b.is_dir()


def test_memory_and_checkpoint_paths_are_per_project(tmp_path):
    project = tmp_path / "my-app"
    project.mkdir()

    mem = memory_db_path(project)
    chk = checkpoint_db_path(project)

    assert mem == project / ".gib" / "memory.db"
    assert chk == project / ".gib" / "checkpoints.db"
    assert mem.parent == chk.parent


def test_log_dir_created_under_project(tmp_path):
    project = tmp_path / "app"
    project.mkdir()

    logs = log_dir_path(project)
    assert logs == project / ".gib" / "logs"
    assert logs.is_dir()


def test_memory_store_uses_project_db(tmp_path):
    from gib.memory.store import MemoryStore

    project = tmp_path / "repo"
    project.mkdir()

    store = MemoryStore(project_root=project)
    store.save_task(
        task_type="general",
        prompt="test task",
        project_path=str(project),
    )

    db_file = project / ".gib" / "memory.db"
    assert db_file.exists()
    tasks = store.recent_tasks(project_path=str(project))
    assert len(tasks) == 1
    assert tasks[0].prompt == "test task"


def test_checkpoint_conn_string_uses_project_path(tmp_path):
    from gib.workflows.checkpoint import checkpoint_conn_string

    project = tmp_path / "repo"
    project.mkdir()

    conn = checkpoint_conn_string(project)
    expected = (project / ".gib" / "checkpoints.db").resolve()
    assert conn == str(expected)
    assert (project / ".gib").is_dir()


def test_checkpoint_conn_string_opens_with_async_sqlite_saver(tmp_path):
    import asyncio

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from gib.workflows.checkpoint import checkpoint_conn_string

    project = tmp_path / "repo"
    project.mkdir()

    async def _open():
        async with AsyncSqliteSaver.from_conn_string(
            checkpoint_conn_string(project)
        ) as checkpointer:
            return checkpointer is not None

    assert asyncio.run(_open()) is True
    assert (project / ".gib" / "checkpoints.db").exists()


def test_ensure_gitignore_creates_file(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()

    changed = ensure_gitignore(project)
    assert changed is True
    content = (project / ".gitignore").read_text(encoding="utf-8")
    assert ".gib/" in content


def test_ensure_gitignore_skips_if_present(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".gitignore").write_text(".gib/\n", encoding="utf-8")

    assert ensure_gitignore(project) is False


def test_ensure_gitignore_appends_to_existing(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    (project / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    assert ensure_gitignore(project) is True
    content = (project / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in content
    assert ".gib/" in content


def test_cleanup_legacy_global_databases(tmp_path, monkeypatch):
    gib_dir = tmp_path / ".gib"
    gib_dir.mkdir()
    memory = gib_dir / "memory.db"
    checkpoints = gib_dir / "checkpoints.db"
    memory.write_text("legacy", encoding="utf-8")
    checkpoints.write_text("legacy", encoding="utf-8")

    monkeypatch.setattr("gib.utils.project_dirs.Path.home", lambda: tmp_path)

    removed = cleanup_legacy_global_databases()
    assert memory in removed
    assert checkpoints in removed
    assert not memory.exists()
    assert not checkpoints.exists()


def test_memory_store_adds_gitignore(tmp_path):
    from gib.memory.store import MemoryStore

    project = tmp_path / "repo"
    project.mkdir()

    MemoryStore(project_root=project)
    assert (project / ".gitignore").read_text(encoding="utf-8").count(".gib/") >= 1
