"""Node: ContextBuilder — собирает контекст проекта без LLM.

Читает README, зависимости, конфигурации, исходные файлы.
Для всех workflow выполняет полный скан проекта и раскладывает файлы по батчам.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from gib.core.state import GibState
from gib.utils import get_logger
from gib.utils.project_root import get_project_root

logger = get_logger("gib.nodes.context_builder")

# Лимиты контекста
_PER_FILE_MAX = 20_000
_CHUNK_SIZE = 40_000
_MAX_TOTAL_CHARS = 2_000_000  # safety cap для огромных монореп

_CONFIG_FILES = [
    "README.md", "README.rst", "README.txt",
    "package.json", "requirements.txt", "pyproject.toml",
    "composer.json", "go.mod", "Cargo.toml", "Gemfile",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    ".gitignore", ".env.example", "Makefile",
    "config.yaml", "render.yaml",
]

_SOURCE_EXTENSIONS = {
    ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs",
    ".java", ".cs", ".rb", ".php", ".cpp", ".c", ".h",
    ".swift", ".kt", ".ex", ".exs",
    ".md", ".yaml", ".yml", ".toml", ".json",
}

_ENTRY_POINT_NAMES = frozenset({
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "index.ts", "index.js", "main.ts", "main.go", "lib.rs",
    "__init__.py",
})

_IGNORE_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build",
    ".venv", "venv", "env", "coverage", ".mypy_cache",
    ".ruff_cache", "target", "vendor", ".pytest_cache",
}


def _read_safe(path: Path, max_chars: int = 8000) -> str:
    """Читает файл с ограничением размера."""
    try:
        content = path.read_text(errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... [truncated, {len(content)} total chars]"
        return content
    except Exception as e:
        logger.debug("Cannot read %s: %s", path, e)
        return ""


def _get_git_changed_files(root: Path) -> set[str]:
    """Файлы изменённые в рабочей директории или последнем коммите."""
    changed: set[str] = set()
    for cmd in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
    ):
        try:
            out = subprocess.check_output(cmd, cwd=root, capture_output=True, text=True, timeout=5)
            for line in out.splitlines():
                line = line.strip()
                if line:
                    changed.add(line)
        except Exception:
            pass
    return changed


def _priority_key(
    path: str,
    *,
    target_paths: set[str],
    git_changed: set[str],
) -> tuple[int, str]:
    """Меньше = выше приоритет при обрезке по total cap."""
    score = 100
    if path in target_paths:
        score = 0
    elif any(path.startswith(t.rstrip("/") + "/") or path == t for t in target_paths):
        score = 10
    if path in git_changed:
        score = min(score, 20)
    if Path(path).name in _ENTRY_POINT_NAMES:
        score = min(score, 30)
    if path.startswith("tests/") or "/tests/" in path:
        score += 40
    return (score, path)


def _find_all_files(
    root: Path,
    target_paths: list[str],
    per_file_max: int = _PER_FILE_MAX,
) -> dict[str, str]:
    """
    Собирает исходные файлы проекта.

    Если указаны target_paths — только они (и их содержимое).
    Иначе — весь проект рекурсивно.
    """
    files: dict[str, str] = {}

    def _collect_dir(directory: Path) -> None:
        for fp in sorted(directory.rglob("*")):
            if not fp.is_file():
                continue
            if any(skip in fp.parts for skip in _IGNORE_DIRS):
                continue
            if fp.suffix not in _SOURCE_EXTENSIONS:
                continue
            content = _read_safe(fp, max_chars=per_file_max)
            if content:
                try:
                    key = str(fp.relative_to(root))
                except ValueError:
                    key = str(fp)
                files[key] = content

    if target_paths:
        for path_str in target_paths:
            p = Path(path_str)
            if not p.is_absolute():
                p = root / p
            if p.is_file():
                content = _read_safe(p, max_chars=per_file_max)
                if content:
                    try:
                        key = str(p.relative_to(root))
                    except ValueError:
                        key = str(p)
                    files[key] = content
            elif p.is_dir():
                _collect_dir(p)
    else:
        _collect_dir(root)

    return files


def _apply_total_cap(
    files: dict[str, str],
    *,
    target_paths: list[str],
    git_changed: set[str],
    max_total: int = _MAX_TOTAL_CHARS,
) -> dict[str, str]:
    """Обрезает набор файлов по приоритету, если превышен safety cap."""
    total = sum(len(v) for v in files.values())
    if total <= max_total:
        return files

    target_set = set(target_paths)
    ordered = sorted(
        files.items(),
        key=lambda kv: _priority_key(kv[0], target_paths=target_set, git_changed=git_changed),
    )
    trimmed: dict[str, str] = {}
    used = 0
    for path, content in ordered:
        if used + len(content) > max_total:
            logger.warning(
                "[context_builder] Safety cap %d chars reached; dropped %d low-priority files",
                max_total,
                len(files) - len(trimmed),
            )
            break
        trimmed[path] = content
        used += len(content)
    return trimmed


def make_file_chunks(
    file_contents: dict[str, str],
    chunk_size: int = 20000,
) -> list[dict[str, str]]:
    """
    Разбивает словарь файлов на батчи по ~chunk_size символов суммарно.
    Каждый батч — dict[path, content], готовый для одного LLM вызова.
    """
    chunks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    current_size = 0

    for path, content in file_contents.items():
        size = len(content)
        if current_size + size > chunk_size and current:
            chunks.append(current)
            current = {}
            current_size = 0
        current[path] = content
        current_size += size

    if current:
        chunks.append(current)

    return chunks if chunks else [{}]


async def node_context_builder(state: GibState) -> dict:
    """
    LangGraph Node: собирает контекст без LLM.

    Полный скан проекта для всех workflow + батчи для chunked review.
    """
    root = get_project_root(state)
    target_paths = state.get("target_paths", [])
    workflow_type = state.get("workflow_type", "")
    meta = state.get("metadata", {})
    free_mode = bool(meta.get("free_mode"))
    per_file_max = int(meta.get("per_file_max_chars", _PER_FILE_MAX if not free_mode else 6000))
    max_total = int(meta.get("max_total_chars", _MAX_TOTAL_CHARS if not free_mode else 200_000))
    logger.info("[context_builder] workflow=%s, target=%s, free=%s", workflow_type, target_paths, free_mode)

    readme_content = ""
    deps_parts: list[str] = []

    for cfg_file in _CONFIG_FILES:
        fp = root / cfg_file
        if not fp.exists():
            continue
        content = _read_safe(fp, max_chars=8000)
        if not content:
            continue
        if cfg_file.startswith("README"):
            readme_content = content
        elif cfg_file in {
            "requirements.txt", "pyproject.toml", "package.json",
            "composer.json", "go.mod", "Cargo.toml", "Gemfile",
            "config.yaml", "render.yaml",
        }:
            deps_parts.append(f"# {cfg_file}\n{content}")

    dependencies_raw = "\n\n".join(deps_parts)
    git_changed = _get_git_changed_files(root)

    file_contents = _find_all_files(root, target_paths, per_file_max=per_file_max)
    if not target_paths:
        file_contents = _apply_total_cap(
            file_contents,
            target_paths=target_paths,
            git_changed=git_changed,
            max_total=max_total,
        )

    chunks = make_file_chunks(file_contents, chunk_size=_CHUNK_SIZE)
    total_chars = sum(len(v) for v in file_contents.values())
    logger.info(
        "[context_builder] Полный скан: %d файлов, %d chars, %d батчей",
        len(file_contents), total_chars, len(chunks),
    )

    metadata_update = {
        "project_chunks": chunks,
        "project_chunks_total": len(chunks),
        "review_chunks": chunks,
        "review_chunks_total": len(chunks),
        "all_project_files": list(file_contents.keys()),
        "git_changed_files": sorted(git_changed),
    }

    relevant_files = list(file_contents.keys())

    return {
        "file_contents": file_contents,
        "relevant_files": relevant_files,
        "readme_content": readme_content,
        "dependencies_raw": dependencies_raw,
        "current_step": "context_built",
        "metadata": metadata_update,
        "logs": [
            f"[ContextBuilder] {len(file_contents)} files, {total_chars} chars, "
            f"{len(chunks)} chunks"
        ],
    }
