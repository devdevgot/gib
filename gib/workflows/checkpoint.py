"""LangGraph checkpoint path helper."""
from __future__ import annotations

from pathlib import Path

from gib.utils.project_dirs import checkpoint_db_path, ensure_project_data_layout


def checkpoint_conn_string(project_root: Path | str | None = None) -> str:
    """Filesystem path for LangGraph AsyncSqliteSaver (aiosqlite file path, not SQLAlchemy URI)."""
    ensure_project_data_layout(project_root)
    return str(checkpoint_db_path(project_root).resolve())
