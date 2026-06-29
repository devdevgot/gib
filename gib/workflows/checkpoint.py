"""LangGraph checkpoint path helper."""
from __future__ import annotations

import sqlite3
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from gib.config import get_config
from gib.utils import get_logger
from gib.utils.project_dirs import (
    aiosqlite_conn_string,
    ensure_project_data_layout,
    find_writable_db_path,
)

logger = get_logger("gib.checkpoint")


def checkpoint_conn_string(project_root: Path | str | None = None) -> str:
    """Filesystem path for LangGraph AsyncSqliteSaver (not a SQLAlchemy URI).

    Guarantees a path that can actually be opened, falling back to per-project
    / home / temp storage when the configured location is unusable.
    """
    ensure_project_data_layout(project_root)
    preferred = get_config().checkpoint_db_path(project_root)
    db_path = find_writable_db_path(preferred, "checkpoints.db", project_root)
    return aiosqlite_conn_string(db_path)


@asynccontextmanager
async def open_checkpoint_saver(project_root: Path | str | None = None):
    """Open the checkpoint saver, retrying on a fresh temp DB if SQLite open fails."""
    primary_conn = checkpoint_conn_string(project_root)

    try:
        async with AsyncSqliteSaver.from_conn_string(primary_conn) as saver:
            yield saver
            return
    except sqlite3.Error:
        fallback_conn = str(Path(tempfile.mkdtemp(prefix="gib-")) / "checkpoints.db")
        logger.warning(
            "Checkpoint DB %s could not be opened; using temporary %s",
            primary_conn,
            fallback_conn,
        )

    async with AsyncSqliteSaver.from_conn_string(fallback_conn) as saver:
        yield saver
