"""Tests for free workflow config helpers."""
from gib.workflows.free_config import FREE_METADATA, is_simple_free_task


def test_free_metadata_limits():
    assert FREE_METADATA["free_mode"] is True
    assert FREE_METADATA["file_finder_max_files"] == 8
    assert FREE_METADATA["per_file_max_chars"] == 6000


def test_simple_task_short_request():
    assert is_simple_free_task("добавь кнопку")
