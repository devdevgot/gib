"""Tests for free-form CLI prompt routing."""
from gib.cli.entrypoint import build_freeform_argv, is_subcommand, parse_freeform_flags
from gib.utils.request import enrich_user_request, expand_keywords, join_prompt_args


def test_join_prompt_args():
    assert join_prompt_args(["улучши", "страницу", "дашборда"]) == "улучши страницу дашборда"


def test_build_freeform_argv_multiline():
    argv = ["gib", "улучши", "страницу", "дашборда"]
    assert build_freeform_argv(argv) == ["gib", "ask", "улучши страницу дашборда"]


def test_build_freeform_argv_with_yes_flag():
    argv = ["gib", "-y", "улучши", "дашборд"]
    assert build_freeform_argv(argv) == ["gib", "ask", "улучши дашборд", "--yes"]


def test_build_freeform_argv_subcommand_unchanged():
    assert build_freeform_argv(["gib", "review", "src/"]) is None
    assert build_freeform_argv(["gib", "set-key"]) is None


def test_build_freeform_argv_help_unchanged():
    assert build_freeform_argv(["gib", "--help"]) is None


def test_is_subcommand():
    assert is_subcommand("fix")
    assert not is_subcommand("улучши")


def test_expand_keywords_russian_dashboard():
    expanded = expand_keywords(["дашборда", "улучши"])
    assert "dashboard" in [k.lower() for k in expanded]


def test_enrich_user_request_adds_agent_instructions():
    result = enrich_user_request("улучши страницу дашборда")
    assert "улучши страницу дашборда" in result
    assert "Самостоятельно определи" in result
