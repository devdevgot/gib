"""Tests for package version."""
from importlib.metadata import version


def test_package_version_matches_pyproject():
    installed = version("gib")
    assert installed == "0.2.3"
