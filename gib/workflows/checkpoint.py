"""LangGraph checkpoint path helper."""
from __future__ import annotations

from gib.config import get_config


def checkpoint_conn_string() -> str:
    """SQLite connection string for LangGraph AsyncSqliteSaver."""
    path = get_config().checkpoint_db_path()
    return f"sqlite:///{path}"
