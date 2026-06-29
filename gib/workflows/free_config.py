"""Конфигурация бесплатного workflow (gibf / gib free)."""
from __future__ import annotations

import re

FREE_MODELS: dict[str, str] = {
    "architect": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "developer": "cohere/north-mini-code:free",
    "reviewer": "poolside/laguna-m.1:free",
    "file_finder": "nvidia/nemotron-3-super-120b-a12b:free",
    "security": "nvidia/nemotron-3-ultra-550b-a55b:free",
}

FREE_METADATA: dict[str, int | bool] = {
    "free_mode": True,
    "max_relevant_files": 8,
    "per_file_max_chars": 6000,
    "max_total_chars": 200_000,
    "file_finder_max_files": 8,
    "file_finder_max_bytes": 6000,
}

MAX_REVIEW_ITERS = 1

_SIMPLE_TASK_RE = re.compile(
    r"\b("
    r"fix|исправ|опечат|typo|rename|переимен|удали|delete|"
    r"format|lint|добавь коммент|add comment|обнови readme|update readme"
    r")\b",
    re.IGNORECASE,
)

_COMPLEX_TASK_RE = re.compile(
    r"\b("
    r"архитект|микросервис|рефактор|refactor|design|спроект|"
    r"полноценн|систем|oauth|аутентификац|authorization|модул"
    r")\b",
    re.IGNORECASE,
)


def is_simple_free_task(request: str) -> bool:
    """Эвристика: простые задачи можно отдать сразу разработчику."""
    text = request.strip()
    if not text:
        return False
    if _COMPLEX_TASK_RE.search(text):
        return False
    words = len(text.split())
    if words <= 4:
        return True
    if words <= 12 and _SIMPLE_TASK_RE.search(text):
        return True
    return False
