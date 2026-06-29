"""Распознавание git-команд из свободного текста (RU/EN)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class GitAction(str, Enum):
    ADD = "add"
    PUSH = "push"
    PULL = "pull"
    MERGE = "merge"
    STATUS = "status"
    COMMIT = "commit"


@dataclass
class GitIntent:
    action: GitAction
    branch: str | None = None
    remote: str = "origin"
    paths: list[str] | None = None
    commit_message: str | None = None
    set_upstream: bool = False


# Явные git-фразы — без них «добавь X» не считается git add
_ADD_RE = re.compile(
    r"(?:"
    r"добавь\s+(?:все\s+)?в\s+гит|добавь\s+(?:все\s+)?в\s+git|"
    r"git\s+add|застейдж|застейджи|stage|в\s+индекс|"
    r"проиндексируй|проиндексируй\s+изменения"
    r")",
    re.IGNORECASE,
)

_PUSH_RE = re.compile(
    r"\b(?:"
    r"пушни|запуш|запушь|push|отправь(?:\s+на)?(?:\s+(?:github|гитхаб|remote|origin))?|"
    r"залей(?:\s+на)?(?:\s+(?:github|гитхаб|remote|origin))?"
    r")\b",
    re.IGNORECASE,
)

_PULL_RE = re.compile(
    r"(?:"
    r"сделай\s+пулл|пуллни|pull|стяни|"
    r"обнови(?:\s+(?:репозиторий|проект|с\s+(?:remote|origin|github|гитхаб)))?|"
    r"подтяни(?:\s+изменения)?"
    r")",
    re.IGNORECASE,
)

_MERGE_RE = re.compile(
    r"\b(?:"
    r"мержни|смержи|merge|влей(?:\s+ветку)?"
    r")\b",
    re.IGNORECASE,
)

_STATUS_RE = re.compile(
    r"(?:"
    r"статус\s+гит|git\s+status|что\s+в\s+гите|покажи\s+статус"
    r")",
    re.IGNORECASE,
)

_COMMIT_RE = re.compile(
    r"(?:"
    r"закоммить|закоммить\s+изменения|сделай\s+коммит|git\s+commit"
    r")",
    re.IGNORECASE,
)

_BRANCH_RE = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9_./-]*",
)


def _extract_branch(text: str) -> str | None:
    """Извлекает имя ветки из фразы после ключевого слова."""
    cleaned = text.strip()
    for prefix in (
        r"мержни\s+",
        r"смержи\s+",
        r"merge\s+",
        r"влей\s+ветку\s+",
        r"влей\s+",
        r"стяни\s+",
        r"pull\s+",
        r"пуллни\s+",
        r"с\s+",
        r"из\s+",
        r"ветк[аиу]\s+",
    ):
        cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE).strip()

    for token in cleaned.split():
        if token.lower() in {"в", "in", "into", "на", "on", "from", "с", "из", "ветку", "branch"}:
            continue
        match = _BRANCH_RE.match(token)
        if match and match.group(0) not in {"origin", "remote", "github", "гитхаб"}:
            return match.group(0)
    return None


def _extract_paths(text: str) -> list[str] | None:
    """Пути файлов после git add (если указаны)."""
    m = re.search(r"git\s+add\s+(.+)$", text, re.IGNORECASE)
    if m:
        return [p for p in m.group(1).split() if p and not p.startswith("-")]
    m = re.search(r"добавь\s+в\s+гит\s+(.+)$", text, re.IGNORECASE)
    if m:
        rest = m.group(1).strip()
        if rest and rest.lower() not in {"всё", "все", "all"}:
            return rest.split()
    return None


def _extract_commit_message(text: str) -> str | None:
    for prefix in ("закоммить", "сделай коммит", "git commit"):
        m = re.search(rf"{prefix}\s+(.+)$", text, re.IGNORECASE)
        if m:
            msg = m.group(1).strip().strip("\"'")
            if msg:
                return msg
    return None


def parse_git_intent(text: str) -> GitIntent | None:
    """Определяет git-намерение из свободной фразы. None — не git-команда."""
    raw = text.strip()
    if not raw:
        return None

    lower = raw.lower()
    set_upstream = any(kw in lower for kw in ("upstream", "апстрим", "-u", "первый раз"))

    if _STATUS_RE.search(raw):
        return GitIntent(action=GitAction.STATUS)

    if _ADD_RE.search(raw):
        return GitIntent(action=GitAction.ADD, paths=_extract_paths(raw))

    if _PUSH_RE.search(raw):
        return GitIntent(
            action=GitAction.PUSH,
            branch=_extract_branch(raw),
            set_upstream=set_upstream or "первый" in lower,
        )

    if _PULL_RE.search(raw):
        return GitIntent(action=GitAction.PULL, branch=_extract_branch(raw))

    if _MERGE_RE.search(raw):
        branch = _extract_branch(raw)
        if not branch:
            return None
        return GitIntent(action=GitAction.MERGE, branch=branch)

    if _COMMIT_RE.search(raw):
        return GitIntent(
            action=GitAction.COMMIT,
            commit_message=_extract_commit_message(raw),
        )

    return None
