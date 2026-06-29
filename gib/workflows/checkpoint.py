"""LangGraph checkpoint path helper."""
from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from gib.config import get_config
from gib.utils.project_dirs import (
    aiosqlite_conn_string,
    checkpoint_db_path as resolve_checkpoint_db_path,
    ensure_project_data_layout,
)


def checkpoint_conn_string(project_root: Path | str | None = None) -> str:
    """Filesystem path for LangGraph AsyncSqliteSaver (not a SQLAlchemy URI)."""
    ensure_project_data_layout(project_root)
    db_path = get_config().checkpoint_db_path(project_root)
    return aiosqlite_conn_string(db_path)


@asynccontextmanager
async def open_checkpoint_saver(project_root: Path | str | None = None):
    """Open the checkpoint saver, retrying with per-project fallback storage when needed."""
    primary_conn = checkpoint_conn_string(project_root)

    try:
        async with AsyncSqliteSaver.from_conn_string(primary_conn) as saver:
            yield saver
            return
    except sqlite3.Error:
        fallback_conn = aiosqlite_conn_string(resolve_checkpoint_db_path(project_root))
        if fallback_conn == primary_conn:
            raise

    async with AsyncSqliteSaver.from_conn_string(fallback_conn) as saver:
        yield saver
