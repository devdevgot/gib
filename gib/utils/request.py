"""Helpers for free-form natural language CLI requests."""
from __future__ import annotations

# Русские синонимы → дополнительные grep-ключи для поиска файлов
_RU_KEYWORD_ALIASES: dict[str, list[str]] = {
    "дашборд": ["dashboard", "Dashboard"],
    "дашборда": ["dashboard", "Dashboard"],
    "страницу": ["page", "Page", "view", "View"],
    "страница": ["page", "Page", "view", "View"],
    "странице": ["page", "Page", "view", "View"],
    "улучши": ["improve", "refactor", "ui", "ux"],
    "улучшить": ["improve", "refactor", "ui", "ux"],
    "исправь": ["fix", "bug", "error"],
    "добавь": ["add", "create", "new"],
    "сделай": ["implement", "create", "add"],
    "компонент": ["component", "Component"],
    "интерфейс": ["ui", "interface", "frontend"],
    "форму": ["form", "Form"],
    "кнопку": ["button", "Button"],
    "меню": ["menu", "nav", "sidebar"],
    "навигац": ["nav", "navigation", "sidebar", "menu"],
    "авторизац": ["auth", "login", "signin"],
    "аутентификац": ["auth", "login", "signin"],
}

_ENRICHMENT_SUFFIX = """

---
Контекст для агентов GIB:
- Самостоятельно определи релевантные файлы, страницы, компоненты, роуты и шаблоны по смыслу запроса.
- Прочитай текущую реализацию в проекте и найди конкретные проблемы (UX, код, производительность, доступность).
- Внеси готовые изменения в код, а не только рекомендации.
- Сохраняй стиль, стек и соглашения проекта.
"""


def join_prompt_args(args: list[str]) -> str:
    """Склеивает аргументы CLI в один запрос пользователя."""
    return " ".join(part.strip() for part in args if part.strip()).strip()


def enrich_user_request(prompt: str) -> str:
    """Дополняет короткий естественный запрос инструкциями для пайплайна."""
    stripped = prompt.strip()
    if not stripped:
        return stripped
    if _ENRICHMENT_SUFFIX.strip() in stripped:
        return stripped
    return stripped + _ENRICHMENT_SUFFIX


def expand_keywords(keywords: list[str]) -> list[str]:
    """Добавляет англоязычные синонимы для русских ключевых слов."""
    expanded: list[str] = []
    seen: set[str] = set()

    def _add(word: str) -> None:
        key = word.lower()
        if key not in seen:
            seen.add(key)
            expanded.append(word)

    for kw in keywords:
        _add(kw)
        for alias in _RU_KEYWORD_ALIASES.get(kw.lower(), []):
            _add(alias)

    return expanded
