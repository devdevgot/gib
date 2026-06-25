"""Node: PatchBuilder — парсит код агента и создаёт список изменений.

НЕ трогает файловую систему на этом этапе.
Только создаёт PatchFile объекты и git diff для показа пользователю.

Применение файлов происходит в node_approval (apply_patches).
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from gib.core.state import GibState
from gib.core.types import PatchFile
from gib.utils import get_logger

logger = get_logger("gib.nodes.patch_builder")

# Паттерн: ### path/to/file.ext (поддерживает подпапки и любые расширения)
_FILE_BLOCK_RE = re.compile(
    r"###\s+(?P<path>[^\n`]+?\.\w+)\s*\n```[\w]*\n(?P<code>[\s\S]+?)```",
    re.MULTILINE,
)

# Альтернативный паттерн: `path/to/file.ext` или **path/to/file.ext**
_ALT_BLOCK_RE = re.compile(
    r"(?:^|\n)\*\*(?P<path>[^\n*]+?\.\w+)\*\*\s*\n```[\w]*\n(?P<code>[\s\S]+?)```",
    re.MULTILINE,
)


def _normalize_path(raw_path: str, root: Path, known_files: set[str]) -> str | None:
    """
    Нормализует путь из LLM-ответа к реальному пути.
    
    Стратегии (в порядке убывания приоритета):
    1. Точное совпадение с known_files
    2. Поиск по суффиксу (имя файла + директория)
    3. Абсолютный путь относительно root
    4. Создание нового файла (путь выглядит валидно)
    """
    raw = raw_path.strip()

    # Убираем leading/trailing пробелы и кавычки
    raw = raw.strip("`\"'")

    # 1. Точное совпадение
    if raw in known_files:
        return raw

    # 2. Поиск по суффиксу пути (LLM иногда добавляет/убирает префикс)
    raw_parts = Path(raw).parts
    for known in known_files:
        known_parts = Path(known).parts
        # Совпадение последних N частей пути
        for n in range(1, min(len(raw_parts), len(known_parts)) + 1):
            if raw_parts[-n:] == known_parts[-n:]:
                return known

    # 3. Проверяем что путь выглядит как валидный файл
    abs_path = root / raw
    if abs_path.exists():
        try:
            return str(abs_path.relative_to(root))
        except ValueError:
            pass

    # 4. Новый файл — путь должен быть относительным и без ../
    if not raw.startswith("/") and ".." not in raw and len(raw) < 200:
        return raw

    return None


def _parse_code_blocks(text: str, root: Path, known_files: set[str]) -> dict[str, str]:
    """
    Извлекает блоки кода из markdown-ответа агента.
    Применяет нормализацию путей.
    """
    result: dict[str, str] = {}

    # Пробуем основной паттерн
    matches = list(_FILE_BLOCK_RE.finditer(text))

    # Если не нашли — пробуем альтернативный
    if not matches:
        matches = list(_ALT_BLOCK_RE.finditer(text))

    for m in matches:
        raw_path = m.group("path").strip()
        code = m.group("code")

        norm_path = _normalize_path(raw_path, root, known_files)
        if norm_path is None:
            logger.warning("[patch_builder] Не удалось нормализовать путь: %r", raw_path)
            continue

        if raw_path != norm_path:
            logger.info("[patch_builder] Путь нормализован: %r → %r", raw_path, norm_path)

        result[norm_path] = code
        logger.info("[patch_builder] Найден блок: %s (%d chars)", norm_path, len(code))

    return result


def _make_diff(original: str, modified: str, filepath: str) -> str:
    """Создаёт unified diff между оригиналом и изменённой версией."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm="",
    ))
    return "\n".join(diff)


def _count_changes(diff: str) -> tuple[int, int]:
    """Считает добавленные и удалённые строки."""
    added = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return added, removed


async def node_patch_builder(state: GibState) -> dict:
    """
    LangGraph Node: строит патч из результата разработчика.

    НЕ изменяет файловую систему.
    Создаёт список PatchFile и git_diff для показа пользователю.
    Реальная запись происходит в node_approval → apply_patches().
    """
    root = Path(state.get("project_context", {}).get("root", str(Path.cwd())))
    code_result = state.get("code_result", "")
    file_contents: dict[str, str] = state.get("file_contents", {})
    relevant_files: list[str] = state.get("relevant_files", [])

    # Множество известных файлов для нормализации путей
    known_files: set[str] = set(relevant_files) | set(file_contents.keys())

    logger.info("[patch_builder] Строю патч, known_files=%d", len(known_files))

    # Парсим файловые блоки
    parsed_files = _parse_code_blocks(code_result, root, known_files)

    if not parsed_files:
        logger.warning("[patch_builder] Не удалось извлечь файловые блоки из кода")
        return {
            "patch_files": [],
            "git_diff": code_result[:5000],
            "approval_summary": (
                "⚠️ Не удалось разобрать файловую структуру из ответа агента.\n"
                "Убедитесь что разработчик форматирует файлы как:\n"
                "  ### path/to/file.py\n"
                "  ```python\n"
                "  <code>\n"
                "  ```"
            ),
            "current_step": "patch_built",
            "logs": ["[PatchBuilder] Could not parse file blocks, raw output available"],
        }

    patch_files: list[PatchFile] = []
    all_diffs: list[str] = []

    for file_path, new_content in parsed_files.items():
        # Определяем оригинал
        abs_path = root / file_path
        if abs_path.exists():
            original = abs_path.read_text(errors="ignore")
        elif file_path in file_contents:
            original = file_contents[file_path]
        else:
            original = ""  # новый файл

        diff = _make_diff(original, new_content, file_path)
        added, removed = _count_changes(diff)

        patch_files.append(PatchFile(
            path=file_path,
            original=original,
            modified=new_content,
            diff=diff,
            lines_added=added,
            lines_removed=removed,
        ))

        if diff:
            all_diffs.append(diff)

        is_new = not bool(original)
        logger.info(
            "[patch_builder] %s %s: +%d/-%d",
            "[NEW]" if is_new else "[MOD]",
            file_path, added, removed,
        )

    total_added = sum(p.lines_added for p in patch_files)
    total_removed = sum(p.lines_removed for p in patch_files)
    git_diff = "\n".join(all_diffs)

    # Summary для Human Approval
    file_list = "\n".join(
        f"  {'[NEW]' if not pf.original else '[MOD]'} {pf.path} "
        f"(+{pf.lines_added}/-{pf.lines_removed})"
        for pf in patch_files
    )
    summary = (
        f"Files to change: {len(patch_files)}\n"
        f"Total: +{total_added} lines / -{total_removed} lines\n\n"
        f"{file_list}"
    )

    logger.info(
        "[patch_builder] Патч готов: %d файлов, +%d/-%d строк",
        len(patch_files), total_added, total_removed,
    )

    return {
        "patch_files": patch_files,
        "git_diff": git_diff,
        "approval_summary": summary,
        "current_step": "patch_built",
        "logs": [
            f"[PatchBuilder] {len(patch_files)} files, +{total_added}/-{total_removed} lines"
        ],
    }
