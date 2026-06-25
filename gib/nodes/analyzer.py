"""Node: ProjectAnalyzer — статический анализ проекта без LLM.

Определяет: язык, framework, package manager, git, docker, env, зависимости, структуру.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from gib.core.state import GibState
from gib.utils import get_logger

logger = get_logger("gib.nodes.analyzer")

# Маппинг файлов → стек
_STACK_MARKERS: dict[str, dict[str, str]] = {
    "package.json": {"language": "JavaScript/TypeScript", "pm": "npm"},
    "requirements.txt": {"language": "Python", "pm": "pip"},
    "pyproject.toml": {"language": "Python", "pm": "pip/uv"},
    "Pipfile": {"language": "Python", "pm": "pipenv"},
    "go.mod": {"language": "Go", "pm": "go modules"},
    "Cargo.toml": {"language": "Rust", "pm": "cargo"},
    "pom.xml": {"language": "Java", "pm": "maven"},
    "build.gradle": {"language": "Java/Kotlin", "pm": "gradle"},
    "composer.json": {"language": "PHP", "pm": "composer"},
    "Gemfile": {"language": "Ruby", "pm": "bundler"},
    "mix.exs": {"language": "Elixir", "pm": "mix"},
}

_FRAMEWORK_MARKERS: dict[str, list[str]] = {
    "fastapi": ["FastAPI"],
    "django": ["Django"],
    "flask": ["Flask"],
    "express": ["Express.js"],
    "nextjs": ["Next.js"],
    "react": ["React"],
    "vue": ["Vue.js"],
    "nuxt": ["Nuxt.js"],
    "nest": ["NestJS"],
    "gin": ["Gin"],
    "actix": ["Actix"],
    "laravel": ["Laravel"],
    "rails": ["Ruby on Rails"],
}


def _detect_frameworks(root: Path, language: str) -> list[str]:
    """Обнаруживает фреймворки по файлам зависимостей."""
    frameworks: list[str] = []
    dep_files = ["package.json", "requirements.txt", "pyproject.toml", "Pipfile", "go.mod", "Cargo.toml"]

    for dep_file in dep_files:
        fp = root / dep_file
        if not fp.exists():
            continue
        try:
            content = fp.read_text(errors="ignore").lower()
            for key, names in _FRAMEWORK_MARKERS.items():
                if key in content:
                    frameworks.extend(names)
        except Exception:
            continue

    return list(dict.fromkeys(frameworks))  # deduplicate, preserve order


def _get_git_info(root: Path) -> dict[str, Any]:
    """Собирает информацию о Git репозитории."""
    git_dir = root / ".git"
    if not git_dir.exists():
        return {"has_git": False}

    info: dict[str, Any] = {"has_git": True}
    try:
        # Текущая ветка
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        info["branch"] = branch

        # Последние 5 коммитов
        log = subprocess.check_output(
            ["git", "log", "--oneline", "-5"],
            cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        info["recent_commits"] = log.splitlines()

        # Изменённые файлы
        status = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        info["changed_files"] = status.splitlines()

        # Remotes
        remotes = subprocess.check_output(
            ["git", "remote", "-v"],
            cwd=root, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        info["remotes"] = remotes.splitlines()[:4]

    except Exception as e:
        info["error"] = str(e)

    return info


def _get_project_structure(root: Path, max_depth: int = 4) -> str:
    """Строит строковое дерево проекта."""
    ignore = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "dist", "build", ".mypy_cache", "coverage", ".pytest_cache",
        ".ruff_cache", "target", "vendor",
    }
    lines: list[str] = []

    def walk(path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            if entry.name in ignore or entry.name.startswith("."):
                continue
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                walk(entry, prefix + extension, depth + 1)

    lines.append(root.name + "/")
    walk(root, "", 1)
    return "\n".join(lines)


async def node_project_analyzer(state: GibState) -> dict:
    """
    LangGraph Node: анализирует проект без LLM.
    
    Returns partial GibState update.
    """
    root = Path.cwd()
    logger.info("[analyzer] Анализирую проект: %s", root)

    # Определяем стек
    language = "Unknown"
    package_manager = "Unknown"
    for marker_file, info in _STACK_MARKERS.items():
        if (root / marker_file).exists():
            language = info["language"]
            package_manager = info["pm"]
            break

    # Дополнительные маркеры
    has_docker = (root / "Dockerfile").exists() or (root / "docker-compose.yml").exists() \
                 or (root / "docker-compose.yaml").exists()
    has_env = (root / ".env").exists() or (root / ".env.example").exists()
    has_ci = (root / ".github" / "workflows").exists() or (root / ".gitlab-ci.yml").exists()
    has_readme = (root / "README.md").exists() or (root / "README.rst").exists()

    frameworks = _detect_frameworks(root, language)

    # Структура
    structure = _get_project_structure(root)

    # Подсчёт файлов по расширениям
    ext_counter: dict[str, int] = {}
    for p in root.rglob("*"):
        if p.is_file() and not any(
            skip in p.parts for skip in [".git", "node_modules", "__pycache__", ".venv"]
        ):
            ext = p.suffix.lower()
            if ext:
                ext_counter[ext] = ext_counter.get(ext, 0) + 1

    # Топ-5 расширений
    top_extensions = sorted(ext_counter.items(), key=lambda x: x[1], reverse=True)[:5]

    project_context: dict[str, Any] = {
        "root": str(root),
        "language": language,
        "package_manager": package_manager,
        "frameworks": frameworks,
        "has_docker": has_docker,
        "has_env": has_env,
        "has_ci": has_ci,
        "has_readme": has_readme,
        "structure": structure,
        "top_extensions": top_extensions,
    }

    repository_context = _get_git_info(root)

    detected_stack: dict[str, Any] = {
        "language": language,
        "frameworks": frameworks,
        "is_monorepo": any(
            (root / d).exists()
            for d in ["packages", "apps", "services", "modules"]
        ),
    }

    logger.info("[analyzer] Стек: %s %s", language, frameworks)

    return {
        "project_context": project_context,
        "repository_context": repository_context,
        "detected_stack": detected_stack,
        "current_step": "analyzed",
        "logs": [f"[ProjectAnalyzer] Detected: {language}, frameworks: {frameworks}"],
    }
