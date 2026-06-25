"""Tests for file_finder merge behavior."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gib.core.state import make_initial_state
from gib.nodes.file_finder import node_file_finder


@pytest.mark.asyncio
async def test_file_finder_merges_existing_contents(tmp_path: Path):
    (tmp_path / "keep.py").write_text("keep content")
    (tmp_path / "select.py").write_text("select content " * 10)

    state = make_initial_state("fix select.py", "feature", project_root=str(tmp_path))
    state["project_context"] = {"root": str(tmp_path), "language": "Python", "frameworks": []}
    state["file_contents"] = {"keep.py": "keep content"}
    state["metadata"] = {"all_project_files": ["keep.py", "select.py"]}

    with patch("gib.nodes.file_finder._llm_select_files", new=AsyncMock(return_value=["select.py"])):
        result = await node_file_finder(state)

    assert "keep.py" in result["file_contents"]
    assert "select.py" in result["file_contents"]
    assert "select.py" in result["relevant_files"]


@pytest.mark.asyncio
async def test_file_finder_skips_llm_when_target_paths_loaded(tmp_path: Path):
    target = tmp_path / "auth.py"
    target.write_text("def auth(): pass")

    state = make_initial_state(
        "fix auth",
        "bugfix",
        target_paths=[str(target)],
        project_root=str(tmp_path),
    )
    state["project_context"] = {"root": str(tmp_path)}
    state["file_contents"] = {"auth.py": "def auth(): pass"}

    result = await node_file_finder(state)
    assert result["relevant_files"] == ["auth.py"]
    assert result["file_contents"]["auth.py"] == "def auth(): pass"
