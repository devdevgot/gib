"""Tests for natural-language git commands."""
from gib.cli.entrypoint import build_freeform_argv
from gib.git.intent import GitAction, parse_git_intent


def test_parse_push_intents():
    assert parse_git_intent("пушни").action == GitAction.PUSH
    assert parse_git_intent("запуш изменения").action == GitAction.PUSH
    assert parse_git_intent("push").action == GitAction.PUSH
    assert parse_git_intent("отправь на github").action == GitAction.PUSH


def test_parse_pull_intents():
    assert parse_git_intent("сделай пулл").action == GitAction.PULL
    assert parse_git_intent("стяни").action == GitAction.PULL
    assert parse_git_intent("pull").action == GitAction.PULL
    assert parse_git_intent("обнови репозиторий").action == GitAction.PULL


def test_parse_merge_intent_with_branch():
    intent = parse_git_intent("мержни main")
    assert intent is not None
    assert intent.action == GitAction.MERGE
    assert intent.branch == "main"


def test_parse_add_intent():
    assert parse_git_intent("добавь в гит").action == GitAction.ADD
    assert parse_git_intent("добавь в git").action == GitAction.ADD
    assert parse_git_intent("git add src/main.py").paths == ["src/main.py"]


def test_parse_status_intent():
    assert parse_git_intent("статус гита").action == GitAction.STATUS


def test_parse_commit_with_message():
    intent = parse_git_intent("закоммить fix: typo in readme")
    assert intent is not None
    assert intent.action == GitAction.COMMIT
    assert intent.commit_message == "fix: typo in readme"


def test_non_git_phrases_return_none():
    assert parse_git_intent("добавь авторизацию") is None
    assert parse_git_intent("улучши страницу дашборда") is None
    assert parse_git_intent("исправь баг в login.py") is None


def test_freeform_argv_routes_git_push():
    argv = build_freeform_argv(["gib", "пушни"])
    assert argv == ["gib", "git", "пушни"]


def test_freeform_argv_routes_git_add():
    argv = build_freeform_argv(["gib", "добавь", "в", "гит"])
    assert argv == ["gib", "git", "добавь в гит"]


def test_freeform_argv_still_routes_dev_task_to_ask():
    argv = build_freeform_argv(["gib", "добавь", "авторизацию"])
    assert argv == ["gib", "ask", "добавь авторизацию"]
