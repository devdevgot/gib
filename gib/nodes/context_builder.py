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


def _find_relevant_files(
    root: Path,
    target_paths: list[str],
    max_files: int = 25,
    max_chars_total: int = 30000,
) -> dict[str, str]:
    """
    Находит и читает релевантные файлы.
    
    Если указаны target_paths — читаем их.
    Иначе — автоматически выбираем исходники.
    """
    files: dict[str, str] = {}
    total_chars = 0

    # Если есть явные пути
    if target_paths:
        for path_str in target_paths:
            p = Path(path_str)
            if not p.is_absolute():
                p = root / p
            if p.is_file():
                content = _read_safe(p, max_chars=15000)
                if content:
                    files[str(p.relative_to(root))] = content
                    total_chars += len(content)
            elif p.is_dir():
                for fp in sorted(p.rglob("*")):
                    if fp.suffix in _SOURCE_EXTENSIONS and fp.is_file():
                        content = _read_safe(fp, max_chars=5000)
                        if content and total_chars + len(content) < max_chars_total:
                            key = str(fp.relative_to(root))
                            files[key] = content
                            total_chars += len(content)
            if total_chars >= max_chars_total:
                break
        return files

    # Автовыбор — приоритет: маленькие файлы, ближние к корню
    candidates: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(skip in p.parts for skip in _IGNORE_DIRS):
            continue
        if p.suffix not in _SOURCE_EXTENSIONS:
            continue
        candidates.append(p)

    # Сортируем: меньший размер, меньшая глубина
    candidates.sort(key=lambda f: (len(f.parts), f.stat().st_size))

    for p in candidates[:max_files]:
        per_file_limit = max(2000, (max_chars_total - total_chars) // max(1, max_files - len(files)))
        content = _read_safe(p, max_chars=per_file_limit)
        if content:
            key = str(p.relative_to(root))
            files[key] = content
            total_chars += len(content)
        if total_chars >= max_chars_total:
            break

    return files


async def node_context_builder(state: GibState) -> dict:
    """
    LangGraph Node: собирает контекст без LLM.
    """
    root = Path(state.get("project_context", {}).get("root", str(Path.cwd())))
    target_paths = state.get("target_paths", [])
    logger.info("[context_builder] Собираю контекст, target=%s", target_paths)

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

    # Исходные файлы
    file_contents = _find_relevant_files(
        root, target_paths, max_files=25, max_chars_total=30000
    )
    relevant_files = list(file_contents.keys())

    # Последний diff (для контекста)
    git_diff_preview = _get_recent_git_diff(root)
    if git_diff_preview:
        logger.info("[context_builder] Последний git diff: %d chars", len(git_diff_preview))

    logger.info(
        "[context_builder] Собрано %d файлов, readme=%d chars, deps=%d chars",
        len(file_contents), len(readme_content), len(dependencies_raw)
    )

    return {
        "file_contents": file_contents,
        "relevant_files": relevant_files,
        "readme_content": readme_content,
        "dependencies_raw": dependencies_raw,
        "current_step": "context_built",
        "logs": [
            f"[ContextBuilder] Loaded {len(file_contents)} source files "
            f"({sum(len(v) for v in file_contents.values())} chars)"
        ],
    }
