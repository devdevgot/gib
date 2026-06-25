"""Tests for project analyzer."""
import pytest
from pathlib import Path
from gib.workspace import ProjectAnalyzer


def test_analyze_gib_project():
    """Analyze GIB's own project directory."""
    analyzer = ProjectAnalyzer(Path(__file__).parent.parent)
    profile = analyzer.analyze()
    assert profile.language == "Python"
    assert profile.has_git is False or profile.has_git is True  # either is fine
    assert isinstance(profile.key_dirs, list)


def test_analyze_returns_profile():
    analyzer = ProjectAnalyzer(Path("/tmp"))
    profile = analyzer.analyze()
    assert profile is not None
    assert profile.root == "/tmp"


def test_profile_summary():
    analyzer = ProjectAnalyzer(Path(__file__).parent.parent)
    profile = analyzer.analyze()
    summary = profile.summary()
    assert "Language" in summary
    assert "Framework" in summary
