"""LangGraph checkpoint path helper."""
from __future__ import annotations

from pathlib import Path

from gib.config import get_config
from gib.utils.project_dirs import aiosqlite_conn_string, ensure_project_data_layout


def checkpoint_conn_string(project_root: Path | str | None = None) -> str:
    """Filesystem path for LangGraph AsyncSqliteSaver (not a SQLAlchemy URI)."""
    ensure_project_data_layout(project_root)
    db_path = get_config().checkpoint_db_path(project_root)
    return aiosqlite_conn_string(db_path)
