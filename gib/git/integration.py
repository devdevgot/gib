"""Git integration using GitPython."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from gib.utils import get_logger

logger = get_logger("gib.git")


class GitIntegration:
    """Wrapper around GitPython for GIB git operations."""

    def __init__(self, repo_path: Path | None = None) -> None:
        self.repo_path = repo_path or Path.cwd()
        self._repo: Optional[object] = None
        self._init_repo()

    def _init_repo(self) -> None:
        try:
            import git
            self._repo = git.Repo(self.repo_path, search_parent_directories=True)
        except Exception as e:
            logger.debug("Git repo not found: %s", e)
            self._repo = None

    @property
    def is_git_repo(self) -> bool:
        return self._repo is not None

    def status(self) -> str:
        """Get git status output."""
        if not self._repo:
            return "Не git-репозиторий"
        try:
            import git
            repo = self._repo  # type: ignore[assignment]
            lines = []
            # Modified files
            for item in repo.index.diff(None):
                lines.append(f"  изменён:    {item.a_path}")
            # Staged files
            for item in repo.index.diff("HEAD"):
                lines.append(f"  в индексе:  {item.a_path}")
            # Untracked files
            for path in repo.untracked_files:
                lines.append(f"  неотслеж.:  {path}")
            if not lines:
                return "Нечего коммитить, рабочее дерево чистое"
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка получения статуса: {e}"

    def diff(self, staged: bool = False, path: str = "") -> str:
        """Get git diff."""
        if not self._repo:
            return ""
        try:
            repo = self._repo  # type: ignore[assignment]
            if staged:
                diff = repo.git.diff("--staged", path) if path else repo.git.diff("--staged")
            else:
                diff = repo.git.diff(path) if path else repo.git.diff()
            return diff
        except Exception as e:
            logger.warning("Git diff failed: %s", e)
            return ""

    def full_diff(self) -> str:
        """Get combined staged + unstaged diff."""
        staged = self.diff(staged=True)
        unstaged = self.diff(staged=False)
        parts = []
        if staged:
            parts.append(f"# Изменения в индексе\n{staged}")
        if unstaged:
            parts.append(f"# Неиндексированные изменения\n{unstaged}")
        return "\n\n".join(parts)

    def commit(self, message: str, add_all: bool = True) -> bool:
        """Create a git commit."""
        if not self._repo:
            return False
        try:
            repo = self._repo  # type: ignore[assignment]
            if add_all:
                repo.git.add("-A")
            repo.index.commit(message)
            logger.info("Committed: %s", message[:60])
            return True
        except Exception as e:
            logger.error("Commit failed: %s", e)
            return False

    def current_branch(self) -> str:
        if not self._repo:
            return "unknown"
        try:
            repo = self._repo  # type: ignore[assignment]
            return repo.active_branch.name
        except Exception:
            return "HEAD (detached)"

    def branches(self) -> list[str]:
        if not self._repo:
            return []
        try:
            repo = self._repo  # type: ignore[assignment]
            return [b.name for b in repo.branches]
        except Exception:
            return []

    def get_file_at_head(self, path: str) -> str:
        """Get file content at HEAD."""
        if not self._repo:
            return ""
        try:
            repo = self._repo  # type: ignore[assignment]
            return repo.git.show(f"HEAD:{path}")
        except Exception:
            return ""

    def file_diff(self, path: str) -> str:
        """Get diff for a specific file."""
        all_diff = self.diff(path=path) or self.diff(staged=True, path=path)
        return all_diff
