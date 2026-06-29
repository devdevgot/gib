"""LangGraph checkpoint path helper."""
from __future__ import annotations

from pathlib import Path

from gib.utils.project_dirs import checkpoint_db_path


def checkpoint_conn_string(project_root: Path | str | None = None) -> str:
    """SQLite connection string for LangGraph AsyncSqliteSaver."""
    path = checkpoint_db_path(project_root)
    return f"sqlite:///{path}"
