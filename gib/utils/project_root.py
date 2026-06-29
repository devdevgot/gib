"""Project root resolution from GibState."""
from __future__ import annotations

from pathlib import Path

from gib.core.state import GibState


def get_project_root(state: GibState) -> Path:
    """Return the resolved project root from state, falling back to cwd."""
    explicit = state.get("project_root")
    if explicit:
        return Path(explicit).expanduser().resolve()
    ctx_root = state.get("project_context", {}).get("root")
    if ctx_root:
        return Path(ctx_root).expanduser().resolve()
    return Path.cwd().resolve()
