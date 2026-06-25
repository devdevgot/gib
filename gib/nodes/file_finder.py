"""Node: FileFinder — семантический поиск релевантных файлов для задачи.

Дополняет (не заменяет) file_contents из context_builder:
- выбирает приоритетные файлы для промптов агентов (relevant_files)
- перечитывает выбранные файлы с увеличенным лимитом
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from gib.core.container import Container
from gib.core.state import GibState
from gib.prompts.locale import RUSSIAN_ONLY
from gib.utils import get_logger
from gib.utils.project_root import get_project_root

logger = get_logger("gib.nodes.file_finder")

_SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".tox", "htmlcov", ".eggs", "*.egg-info",
}
_SKIP_EXTS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz", ".lock",
    ".min.js", ".min.css",
}

_FINDER_SYSTEM = f"""\
Ты — навигатор по кодовой базе. По задаче и списку файлов проекта \
выбери наиболее релевантные файлы, которые нужно ПРОЧИТАТЬ или ИЗМЕНИТЬ для выполнения задачи.

Правила:
- Выбери не более 40 файлов
- Предпочитай конкретику: файлы, напрямую связанные с задачей
- Всегда включай __init__.py для изменяемых пакетов
- Всегда включай конфигурационные файлы, если задача затрагивает настройки
- Верни ТОЛЬКО JSON-массив относительных путей к файлам, без пояснений

Пример ответа:
["gib/nodes/developer.py", "gib/core/state.py", "gib/workflows/feature.py"]

{RUSSIAN_ONLY}
"""

_MAX_FILES_IN_PROMPT = 400


def _extract_keywords(task: str) -> list[str]:
    """Извлекает ключевые слова для grep из текста задачи."""
    stop = {
        "the", "a", "an", "in", "of", "to", "and", "or", "for",
        "is", "it", "this", "that", "with", "on", "at", "by", "from",
        "как", "и", "в", "на", "с", "по", "для", "из", "что", "это",
        "не", "он", "она", "они", "мы", "вы", "я", "но", "а", "же",
    }
    words = re.findall(r"[a-zA-Zа-яА-Я_][a-zA-Zа-яА-Я_0-9]{2,}", task)
    keywords = [w for w in words if w.lower() not in stop]
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        kl = kw.lower()
        if kl not in seen:
            seen.add(kl)
            result.append(kw)
        if len(result) >= 10:
            break
    return result


def _list_all_files(root: Path) -> list[str]:
    """Рекурсивно обходит проект, возвращает пути относительно root."""
    result: list[str] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        parts = p.parts
        if any(part in _SKIP_DIRS or part.endswith(".egg-info") for part in parts):
            continue
        if p.suffix in _SKIP_EXTS or p.name.endswith(".min.js") or p.name.endswith(".min.css"):
            continue
        rel = str(p.relative_to(root))
        result.append(rel)
    return sorted(result)


def _grep_candidates(root: Path, keywords: list[str]) -> list[str]:
    """Запускает ripgrep по ключевым словам, возвращает файлы-кандидаты."""
    if not keywords:
        return []
    candidates: set[str] = set()
    for kw in keywords:
        try:
            result = subprocess.run(
                ["rg", "--files-with-matches", "-i", "--max-count=1",
                 "--glob=!.git", "--glob=!.venv", "--glob=!__pycache__",
                 kw, str(root)],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                path = Path(line.strip())
                if path.exists():
                    try:
                        rel = str(path.relative_to(root))
                        if not any(skip in rel for skip in _SKIP_DIRS):
                            candidates.add(rel)
                    except ValueError:
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return sorted(candidates)


def _summarize_file_list(all_files: list[str], candidates: list[str]) -> str:
    """Сжатый список файлов для LLM — не отправляем весь репозиторий."""
    if len(all_files) <= _MAX_FILES_IN_PROMPT:
        return "\n".join(all_files)
    candidate_set = set(candidates)
    priority = [f for f in all_files if f in candidate_set]
    rest = [f for f in all_files if f not in candidate_set]
    head = priority[:200]
    tail_budget = _MAX_FILES_IN_PROMPT - len(head)
    if tail_budget > 0:
        head.extend(rest[:tail_budget])
    omitted = len(all_files) - len(head)
    summary = "\n".join(head)
    if omitted > 0:
        summary += f"\n... [ещё {omitted} файлов не показано в списке]"
    return summary


async def _llm_select_files(
    task: str,
    all_files: list[str],
    candidates: list[str],
    project_context: dict,
    session_context: str = "",
) -> list[str]:
    """LLM выбирает топ релевантных файлов."""
    from gib.config.loader import get_config
    container = Container.instance()
    client = container.openrouter_client()

    from gib.providers import ChatMessage
    _model = get_config().models.cheap or "deepseek/deepseek-v3.2"

    all_files_str = _summarize_file_list(all_files, candidates)
    candidates_str = "\n".join(candidates) if candidates else "(не найдено)"
    memory_block = f"\n## Контекст проекта из памяти\n{session_context[:3000]}\n" if session_context else ""

    prompt = f"""\
## Задача
{task}
{memory_block}
## Информация о проекте
Язык: {project_context.get('language', 'неизвестен')}
Фреймворки: {', '.join(project_context.get('frameworks', []))}

## Кандидаты grep (файлы с ключевыми словами задачи)
{candidates_str}

## Файлы проекта
{all_files_str}

Выбери наиболее релевантные файлы. Верни ТОЛЬКО JSON-массив путей."""

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_FINDER_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=_model,
        temperature=0.0,
        max_tokens=2048,
    )

    content = resp.content.strip()
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", content)
        if m:
            content = m.group(1)
    m = re.search(r"\[[\s\S]*\]", content)
    if m:
        try:
            paths = json.loads(m.group(0))
            return [p for p in paths if isinstance(p, str)]
        except json.JSONDecodeError:
            pass

    logger.warning("[file_finder] LLM вернул неверный JSON, используем кандидатов")
    return candidates[:40]


def _read_files(root: Path, rel_paths: list[str], max_bytes: int = 100_000) -> dict[str, str]:
    """Читает файлы, обрезает до max_bytes каждый."""
    result: dict[str, str] = {}
    for rel in rel_paths:
        abs_path = root / rel
        if not abs_path.exists():
            logger.warning("[file_finder] Файл не найден: %s", rel)
            continue
        try:
            content = abs_path.read_text(errors="ignore")
            if len(content) > max_bytes:
                content = content[:max_bytes] + f"\n\n... [обрезано, всего {len(content)} байт]"
            result[rel] = content
        except Exception as e:
            logger.warning("[file_finder] Ошибка чтения %s: %s", rel, e)
    return result


async def node_file_finder(state: GibState) -> dict:
    """
    LangGraph Node: находит релевантные файлы для задачи.

    Дополняет file_contents из context_builder (merge, не replace).
    relevant_files — приоритетный список для промптов агентов.
    """
    task = state.get("user_request", "")
    ctx = state.get("project_context", {})
    root = get_project_root(state)
    target_paths = state.get("target_paths", [])
    existing_contents: dict[str, str] = dict(state.get("file_contents", {}))
    session_context = state.get("session_context", "")

    logger.info("[file_finder] Ищу релевантные файлы в %s", root)

    # Явные target_paths — context_builder уже загрузил нужное
    if target_paths and existing_contents:
        selected = list(existing_contents.keys())
        logger.info("[file_finder] Используем %d файлов из target_paths", len(selected))
        return {
            "relevant_files": selected,
            "file_contents": existing_contents,
            "logs": [f"[FileFinder] Using {len(selected)} target path files (no LLM selection)"],
        }

    all_files = state.get("metadata", {}).get("all_project_files") or _list_all_files(root)
    logger.info("[file_finder] Всего файлов: %d", len(all_files))

    keywords = _extract_keywords(task)
    candidates = _grep_candidates(root, keywords)
    logger.info("[file_finder] grep-кандидаты: %d файлов", len(candidates))

    git_changed = set(state.get("metadata", {}).get("git_changed_files", []))
    for path in git_changed:
        if path not in candidates:
            candidates.append(path)

    relevant = await _llm_select_files(
        task, all_files, candidates, ctx, session_context=session_context,
    )
    logger.info("[file_finder] LLM выбрал: %d файлов", len(relevant))

    valid: list[str] = []
    for rel in relevant:
        if (root / rel).exists():
            valid.append(rel)
        else:
            logger.warning("[file_finder] Выбранный файл не существует: %s", rel)

    if len(valid) < 3 and candidates:
        for c in candidates:
            if c not in valid:
                valid.append(c)
        valid = valid[:40]

    # Merge: сохраняем полный скан + обновляем выбранные файлы с большим лимитом
    upgraded = _read_files(root, valid, max_bytes=100_000)
    merged_contents = {**existing_contents, **upgraded}

    # relevant_files — приоритет для агентов; git-changed идут первыми
    priority = [p for p in git_changed if p in merged_contents]
    for p in valid:
        if p not in priority:
            priority.append(p)

    return {
        "relevant_files": priority[:40],
        "file_contents": merged_contents,
        "logs": [
            f"[FileFinder] {len(priority)} priority files, "
            f"{len(merged_contents)} total in context "
            f"(from {len(all_files)} project files)"
        ],
    }
