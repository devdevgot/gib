"""Project Analyzer — auto-detects language, framework, stack, and structure."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from gib.utils import get_logger

logger = get_logger("gib.workspace.analyzer")


class ProjectProfile(BaseModel):
    root: str = ""
    language: str = "unknown"
    framework: str = "unknown"
    package_manager: str = "unknown"
    has_git: bool = False
    has_docker: bool = False
    has_readme: bool = False
    has_env: bool = False
    has_tests: bool = False
    has_ci: bool = False
    entry_points: list[str] = Field(default_factory=list)
    key_dirs: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    architecture_notes: str = ""

    def summary(self) -> str:
        lines = [
            f"  Language:        {self.language}",
            f"  Framework:       {self.framework}",
            f"  Package manager: {self.package_manager}",
            f"  Git:             {'yes' if self.has_git else 'no'}",
            f"  Docker:          {'yes' if self.has_docker else 'no'}",
            f"  Tests:           {'yes' if self.has_tests else 'no'}",
            f"  CI:              {'yes' if self.has_ci else 'no'}",
        ]
        if self.key_dirs:
            lines.append(f"  Key dirs:        {', '.join(self.key_dirs[:8])}")
        return "\n".join(lines)


# ── Detection helpers ─────────────────────────────────────────────────────────

_LANG_INDICATORS: list[tuple[str, list[str]]] = [
    ("Python",      ["*.py", "pyproject.toml", "setup.py", "requirements.txt", "Pipfile"]),
    ("JavaScript",  ["package.json", "*.js", "*.mjs"]),
    ("TypeScript",  ["tsconfig.json", "*.ts"]),
    ("Go",          ["go.mod", "*.go"]),
    ("Rust",        ["Cargo.toml", "*.rs"]),
    ("Java",        ["pom.xml", "build.gradle", "*.java"]),
    ("PHP",         ["composer.json", "*.php"]),
    ("Ruby",        ["Gemfile", "*.rb"]),
    ("C#",          ["*.csproj", "*.cs"]),
    ("C/C++",       ["CMakeLists.txt", "Makefile", "*.c", "*.cpp", "*.h"]),
]

_FRAMEWORK_INDICATORS: dict[str, list[str]] = {
    "FastAPI":   ["fastapi", "uvicorn"],
    "Django":    ["django"],
    "Flask":     ["flask"],
    "Next.js":   ["next", "next.config.js", "next.config.ts"],
    "React":     ["react", "react-dom"],
    "Vue":       ["vue", "@vue"],
    "Angular":   ["@angular"],
    "NestJS":    ["@nestjs"],
    "Express":   ["express"],
    "Laravel":   ["laravel"],
    "Spring":    ["spring-boot"],
    "WordPress": ["wp-config.php", "wp-content"],
}

_PM_FILES: dict[str, str] = {
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "bun",
    "Pipfile.lock": "pipenv",
    "poetry.lock": "poetry",
    "pdm.lock": "pdm",
    "uv.lock": "uv",
    "requirements.txt": "pip",
    "Cargo.lock": "cargo",
    "go.sum": "go mod",
    "composer.lock": "composer",
    "Gemfile.lock": "bundler",
}

_TEST_DIRS = {"tests", "test", "__tests__", "spec", "e2e"}
_CI_FILES = {".github", ".gitlab-ci.yml", ".circleci", "Jenkinsfile", ".travis.yml"}


def _files_in(root: Path, max_depth: int = 2) -> list[str]:
    """List filenames up to max_depth levels deep."""
    result: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth >= max_depth:
            dirnames.clear()
        for fn in filenames:
            result.append(fn)
        # Include dir names too
        result.extend(dirnames)
    return result


def _read_text_safe(path: Path, max_bytes: int = 8192) -> str:
    try:
        return path.read_text(errors="ignore")[:max_bytes]
    except Exception:
        return ""


class ProjectAnalyzer:
    """Analyzes the current project directory."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()

    def analyze(self) -> ProjectProfile:
        root = self.root
        all_names = _files_in(root, max_depth=3)
        names_set = set(all_names)

        profile = ProjectProfile(root=str(root))

        # Git / Docker / Readme / Env
        profile.has_git = (root / ".git").exists()
        profile.has_docker = "Dockerfile" in names_set or "docker-compose.yml" in names_set
        profile.has_readme = any(n.lower().startswith("readme") for n in names_set)
        profile.has_env = ".env" in names_set or ".env.example" in names_set
        profile.has_tests = bool(_TEST_DIRS & names_set)
        profile.has_ci = bool(_CI_FILES & names_set)

        # Language detection
        for lang, indicators in _LANG_INDICATORS:
            for ind in indicators:
                if "*" in ind:
                    ext = ind.lstrip("*")
                    if any(n.endswith(ext) for n in all_names):
                        profile.language = lang
                        break
                elif ind in names_set:
                    profile.language = lang
                    break
            if profile.language != "unknown":
                break

        # Package manager
        for fname, pm in _PM_FILES.items():
            if fname in names_set:
                profile.package_manager = pm
                break

        # Framework detection — read package.json or requirements.txt
        profile.framework = self._detect_framework(root, names_set, all_names)

        # Key dirs (top-level)
        key_dirs = [
            d.name
            for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
            and d.name not in {"node_modules", "__pycache__", ".git", "dist", "build", ".venv", "venv"}
        ]
        profile.key_dirs = sorted(key_dirs)[:12]

        # Key files (top-level)
        key_files = [
            f.name for f in root.iterdir() if f.is_file()
        ]
        profile.key_files = sorted(key_files)[:20]

        logger.debug("Project analyzed: %s", profile.model_dump())
        return profile

    def _detect_framework(self, root: Path, names_set: set[str], all_names: list[str]) -> str:
        # Check package.json deps
        pkg_json = root / "package.json"
        if pkg_json.exists():
            text = _read_text_safe(pkg_json)
            for fw, indicators in _FRAMEWORK_INDICATORS.items():
                if any(ind in text for ind in indicators):
                    return fw

        # Check Python requirements
        for req_file in ["requirements.txt", "pyproject.toml", "Pipfile"]:
            p = root / req_file
            if p.exists():
                text = _read_text_safe(p).lower()
                for fw, indicators in _FRAMEWORK_INDICATORS.items():
                    if any(ind.lower() in text for ind in indicators):
                        return fw

        # Check file-based indicators
        for fw, indicators in _FRAMEWORK_INDICATORS.items():
            for ind in indicators:
                if ind in names_set:
                    return fw

        return "unknown"
