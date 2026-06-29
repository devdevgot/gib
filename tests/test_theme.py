"""Tests for terminal theme."""
from gib.utils.theme import GIB_THEME, GREEN, prompt_prefix


def test_theme_has_green_brand():
    brand_style = str(GIB_THEME.styles["brand"])
    assert GREEN in brand_style or "00FF87" in brand_style.upper()


def test_prompt_prefix():
    assert "❯" in prompt_prefix()
