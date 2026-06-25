"""Node: PatchBuilder — создаёт патч и Git diff без изменения файлов.

Не трогает файловую систему. Только готовит изменения.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from gib.core.state import GibState
from gib.core.types import PatchFile
from gib.utils import get_logger

logger = get_logger("gib.nodes.patch_builder")

_FILE_BLOCK_RE = re.compile(
    r"###\s+(?P<path>[\w./\-]+\.\w+)\s*\n```[\w]*\n(?P<code>[\s\S]+?)```",
    re.MULTILINE
)


def _parse_code_blocks(text: str) -> dict[str, str]:
    """Извлекает блоки кода из markdown-ответа агента."""
    result: dict[str, str] = {}
    for m in _FILE_BLOCK_RE.finditer(text):
        path = m.group("path").strip()
        code = m.group("code")
        result[path] = code
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
    Только создаёт список PatchFile и git_diff.
    """
    root = Path(state.get("project_context", {}).get("root", str(Path.cwd())))
    code_result = state.get("code_result", "")
    file_contents = state.get("file_contents", {})

    logger.info("[patch_builder] Строю патч из кода агента")

    # Парсим файловые блоки из кода разработчика
    parsed_files = _parse_code_blocks(code_result)

    if not parsed_files:
        logger.warning("[patch_builder] Не удалось извлечь файловые блоки из кода")
        # Возвращаем весь код как один патч
        return {
            "patch_files": [],
            "git_diff": code_result[:5000],
            "approval_summary": "Не удалось разобрать файловую структуру. Проверьте вывод вручную.",
            "current_step": "patch_built",
            "logs": ["[PatchBuilder] Could not parse file blocks, raw output available"],
        }

    patch_files: list[PatchFile] = []
    all_diffs: list[str] = []

    for file_path, new_content in parsed_files.items():
        # Читаем оригинал
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

        logger.info("[patch_builder] %s: +%d/-%d", file_path, added, removed)

    total_added = sum(p.lines_added for p in patch_files)
    total_removed = sum(p.lines_removed for p in patch_files)
    git_diff = "\n".join(all_diffs)

    # Строим summary для Human Approval
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
        "[patch_builder] Патч: %d файлов, +%d/-%d строк",
        len(patch_files), total_added, total_removed
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
