"""Node: ContextBuilder — собирает контекст проекта без LLM.

Читает README, зависимости, конфигурации, исходные файлы.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from gib.core.state import GibState
from gib.utils import get_logger

logger = get_logger("gib.nodes.context_builder")

# Файлы конфигурации, которые всегда читаем
_CONFIG_FILES = [
    "README.md", "README.rst", "README.txt",
    "package.json", "requirements.txt", "pyproject.toml",
    "composer.json", "go.mod", "Cargo.toml", "Gemfile",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    ".gitignore", ".env.example", "Makefile",
]

_SOURCE_EXTENSIONS = {
    ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs",
    ".java", ".cs", ".rb", ".php", ".cpp", ".c", ".h",
    ".swift", ".kt", ".ex", ".exs",
}

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


def _get_recent_git_diff(root: Path) -> str:
    """Получает diff последнего коммита."""
    try:
        return subprocess.check_output(
            ["git", "diff", "HEAD~1", "HEAD", "--stat"],
            cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ""


def _find_all_files(
    root: Path,
    target_paths: list[str],
    per_file_max: int = 10000,
) -> dict[str, str]:
    """
    Собирает ВСЕ исходные файлы без общего лимита.

    Если указаны target_paths — только они.
    Иначе — весь проект рекурсивно.
    Каждый файл обрезается до per_file_max символов чтобы не раздувать один файл.
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
            if p.is_file() and p.suffix in _SOURCE_EXTENSIONS:
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
        # Если один файл больше chunk_size — всё равно кладём его отдельно
        if current_size + size > chunk_size and current:
            chunks.append(current)
            current = {}
            current_size = 0
        current[path] = content
        current_size += size

    if current:
        chunks.append(current)

    return chunks if chunks else [{}]


# Экспортируем для использования в reviewer
def _find_relevant_files(
    root: Path,
    target_paths: list[str],
    max_files: int = 25,
    max_chars_total: int = 30000,
) -> dict[str, str]:
    """Legacy — используется в не-review workflow для быстрого контекста."""
    return _find_all_files(root, target_paths, per_file_max=5000)


async def node_context_builder(state: GibState) -> dict:
    """
    LangGraph Node: собирает контекст без LLM.

    Для review workflow — собирает ВСЕ файлы проекта и раскладывает по батчам.
    Для остальных workflow — быстрый контекст (топ файлы).
    """
    root = Path(state.get("project_context", {}).get("root", str(Path.cwd())))
    target_paths = state.get("target_paths", [])
    workflow_type = state.get("workflow_type", "")
    logger.info("[context_builder] workflow=%s, target=%s", workflow_type, target_paths)

    # Конфигурационные файлы
    readme_content = ""
    deps_parts: list[str] = []

    for cfg_file in _CONFIG_FILES:
        fp = root / cfg_file
        if not fp.exists():
            continue
        content = _read_safe(fp, max_chars=5000)
        if not content:
            continue
        if cfg_file.startswith("README"):
            readme_content = content
        elif cfg_file in {"requirements.txt", "pyproject.toml", "package.json",
                           "composer.json", "go.mod", "Cargo.toml", "Gemfile"}:
            deps_parts.append(f"# {cfg_file}\n{content}")

    dependencies_raw = "\n\n".join(deps_parts)

    # Review workflow — собираем ВСЕ файлы, разбиваем на батчи
    if workflow_type in ("review", "doctor"):
        file_contents = _find_all_files(root, target_paths, per_file_max=10000)
        chunks = make_file_chunks(file_contents, chunk_size=20000)
        total_chars = sum(len(v) for v in file_contents.values())
        logger.info(
            "[context_builder] Полный скан: %d файлов, %d chars, %d батчей",
            len(file_contents), total_chars, len(chunks),
        )
        metadata_update = {"review_chunks": chunks, "review_chunks_total": len(chunks)}
    else:
        # Остальные workflow — быстрый контекст
        file_contents = _find_all_files(root, target_paths, per_file_max=5000)
        # Ограничиваем до 30k для скорости
        trimmed: dict[str, str] = {}
        total = 0
        for k, v in file_contents.items():
            if total + len(v) > 30000:
                break
            trimmed[k] = v
            total += len(v)
        file_contents = trimmed
        metadata_update = {}
        logger.info(
            "[context_builder] Быстрый контекст: %d файлов, %d chars",
            len(file_contents), sum(len(v) for v in file_contents.values()),
        )

    relevant_files = list(file_contents.keys())

    result = {
        "file_contents": file_contents,
        "relevant_files": relevant_files,
        "readme_content": readme_content,
        "dependencies_raw": dependencies_raw,
        "current_step": "context_built",
        "logs": [
            f"[ContextBuilder] {len(file_contents)} files, "
            f"{sum(len(v) for v in file_contents.values())} chars"
        ],
    }
    if metadata_update:
        result["metadata"] = metadata_update
    return result
