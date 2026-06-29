"""Per-project data directories (.gib/ inside each project)."""
from __future__ import annotations

from pathlib import Path


def resolve_project_root(project_root: Path | str | None = None) -> Path:
    """Resolve project root, defaulting to the current working directory."""
    if project_root:
        return Path(project_root).expanduser().resolve()
    return Path.cwd().resolve()


def project_data_dir(project_root: Path | str | None = None) -> Path:
    """Return <project>/.gib, creating the directory if needed."""
    root = resolve_project_root(project_root)
    data_dir = root / ".gib"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def memory_db_path(project_root: Path | str | None = None) -> Path:
    """SQLite path for project memory (tasks, chat, paused runs)."""
    return project_data_dir(project_root) / "memory.db"


def checkpoint_db_path(project_root: Path | str | None = None) -> Path:
    """SQLite path for LangGraph checkpoints (gib resume)."""
    return project_data_dir(project_root) / "checkpoints.db"


def log_dir_path(project_root: Path | str | None = None) -> Path:
    """Log directory for a project."""
    log_dir = project_data_dir(project_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
