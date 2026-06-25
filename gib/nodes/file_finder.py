"""Node: FileFinder — семантический поиск релевантных файлов для задачи.

Двухшаговый подход:
1. ripgrep по ключевым словам из задачи → кандидаты
2. LLM выбирает топ-20 файлов из полного списка + кандидатов

Записывает в state:
  - relevant_files: list[str]  — пути относительно root
  - file_contents: dict        — только релевантные файлы, полный контент
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

from gib.core.container import Container
from gib.core.state import GibState
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

_FINDER_SYSTEM = """\
You are a code navigator. Given a task and a list of files in a project, \
select the most relevant files that will need to be READ or MODIFIED to complete the task.

Rules:
- Select at most 30 files
- Prefer specificity: pick the files most directly related to the task
- Always include __init__.py files for modified packages
- Always include config files if the task touches configuration
- Return ONLY a JSON array of relative file paths, nothing else

Example output:
["gib/nodes/developer.py", "gib/core/state.py", "gib/workflows/feature.py"]
"""


def _extract_keywords(task: str) -> list[str]:
    """Извлекает ключевые слова для grep из текста задачи."""
    # Убираем стоп-слова и берём значимые токены
    stop = {
        "the", "a", "an", "in", "of", "to", "and", "or", "for",
        "is", "it", "this", "that", "with", "on", "at", "by", "from",
        "как", "и", "в", "на", "с", "по", "для", "из", "что", "это",
        "не", "он", "она", "они", "мы", "вы", "я", "но", "а", "же",
    }
    words = re.findall(r"[a-zA-Zа-яА-Я_][a-zA-Zа-яА-Я_0-9]{2,}", task)
    keywords = [w for w in words if w.lower() not in stop]
    # Берём уникальные, не более 10
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
        # Пропускаем служебные директории
        parts = p.parts
        if any(part in _SKIP_DIRS or part.endswith(".egg-info") for part in parts):
            continue
        # Пропускаем расширения
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


async def _llm_select_files(
    task: str,
    all_files: list[str],
    candidates: list[str],
    project_context: dict,
) -> list[str]:
    """LLM выбирает топ-20 релевантных файлов."""
    from gib.config.loader import get_config
    container = Container.instance()
    client = container.openrouter_client()

    from gib.providers import ChatMessage
    _model = get_config().models.cheap or "deepseek/deepseek-chat"

    all_files_str = "\n".join(all_files)
    candidates_str = "\n".join(candidates) if candidates else "(none found)"

    prompt = f"""\
## Task
{task}

## Project Info
Language: {project_context.get('language', 'Unknown')}
Frameworks: {', '.join(project_context.get('frameworks', []))}

## Grep Candidates (files containing task keywords)
{candidates_str}

## All Project Files
{all_files_str}

Select the most relevant files. Return ONLY a JSON array of paths."""

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_FINDER_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=_model,
        temperature=0.0,
        max_tokens=1024,
    )

    # Парсим JSON из ответа
    content = resp.content.strip()
    # Убираем markdown-обёртку если есть
    if "```" in content:
        m = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", content)
        if m:
            content = m.group(1)
    # Ищем JSON массив
    m = re.search(r"\[[\s\S]*\]", content)
    if m:
        try:
            paths = json.loads(m.group(0))
            return [p for p in paths if isinstance(p, str)]
        except json.JSONDecodeError:
            pass

    logger.warning("[file_finder] LLM вернул неверный JSON, используем кандидатов")
    return candidates[:30]


def _read_files(root: Path, rel_paths: list[str], max_bytes: int = 80_000) -> dict[str, str]:
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
                content = content[:max_bytes] + f"\n\n... [truncated, {len(content)} bytes total]"
            result[rel] = content
        except Exception as e:
            logger.warning("[file_finder] Ошибка чтения %s: %s", rel, e)
    return result


async def node_file_finder(state: GibState) -> dict:
    """
    LangGraph Node: находит релевантные файлы для задачи.

    Вход:  state["user_request"], state["project_context"]
    Выход: state["relevant_files"] (list[str])
           state["file_contents"]  (dict[str, str]) — перезаписывает предыдущий
    """
    task = state.get("user_request", "")
    ctx = state.get("project_context", {})
    root = get_project_root(state)

    logger.info("[file_finder] Ищу релевантные файлы в %s", root)

    # 1. Список всех файлов
    all_files = _list_all_files(root)
    logger.info("[file_finder] Всего файлов: %d", len(all_files))

    # 2. grep-кандидаты
    keywords = _extract_keywords(task)
    logger.info("[file_finder] Ключевые слова: %s", keywords)
    candidates = _grep_candidates(root, keywords)
    logger.info("[file_finder] grep-кандидаты: %d файлов", len(candidates))

    # 3. LLM выбирает
    relevant = await _llm_select_files(task, all_files, candidates, ctx)
    logger.info("[file_finder] LLM выбрал: %d файлов", len(relevant))

    # Валидация: оставляем только существующие + нормализуем пути
    valid: list[str] = []
    for rel in relevant:
        abs_p = root / rel
        if abs_p.exists():
            valid.append(rel)
        else:
            logger.warning("[file_finder] Выбранный файл не существует: %s", rel)

    # Если LLM выбрал мало — добавляем кандидатов от grep
    if len(valid) < 3 and candidates:
        for c in candidates:
            if c not in valid:
                valid.append(c)
        valid = valid[:30]

    # 4. Читаем файлы
    file_contents = _read_files(root, valid, max_bytes=60_000)
    logger.info("[file_finder] Прочитано: %d файлов", len(file_contents))

    return {
        "relevant_files": valid,
        "file_contents": file_contents,
        "logs": [
            f"[FileFinder] {len(valid)} relevant files selected "
            f"(from {len(all_files)} total, {len(candidates)} grep hits)"
        ],
    }
