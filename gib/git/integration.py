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
            self.repo_path = Path(self._repo.working_dir)
        except Exception as e:
            logger.debug("Git repo not found: %s", e)
            self._repo = None

    @property
    def is_git_repo(self) -> bool:
        return self._repo is not None

    def _repo_git(self):
        if not self._repo:
            raise RuntimeError("Не git-репозиторий")
        return self._repo.git  # type: ignore[union-attr]

    def status(self) -> str:
        """Get git status output."""
        if not self._repo:
            return "Не git-репозиторий"
        try:
            lines = []
            repo = self._repo  # type: ignore[assignment]
            for item in repo.index.diff(None):
                lines.append(f"  изменён:    {item.a_path}")
            for item in repo.index.diff("HEAD"):
                lines.append(f"  в индексе:  {item.a_path}")
            for path in repo.untracked_files:
                lines.append(f"  неотслеж.:  {path}")
            if not lines:
                return "Нечего коммитить, рабочее дерево чистое"
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка получения статуса: {e}"

    def status_summary(self) -> tuple[bool, str]:
        """Краткий статус: ветка + изменения."""
        if not self._repo:
            return False, "Не git-репозиторий"
        branch = self.current_branch()
        short = self._repo_git().status("-sb")
        body = self.status()
        return True, f"Ветка: {branch}\n\n{short}\n\n{body}"

    def diff(self, staged: bool = False, path: str = "") -> str:
        """Get git diff."""
        if not self._repo:
            return ""
        try:
            if staged:
                return self._repo_git().diff("--staged", path) if path else self._repo_git().diff("--staged")
            return self._repo_git().diff(path) if path else self._repo_git().diff()
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

    def add(self, paths: list[str] | None = None) -> tuple[bool, str]:
        """git add — в индекс."""
        try:
            if paths:
                self._repo_git().add(*paths)
                return True, f"Добавлено в индекс: {', '.join(paths)}"
            self._repo_git().add("-A")
            return True, "Все изменения добавлены в индекс (git add -A)"
        except Exception as e:
            logger.error("git add failed: %s", e)
            return False, f"git add не удался: {e}"

    def commit(self, message: str, add_all: bool = True) -> bool:
        """Create a git commit."""
        ok, _ = self.commit_with_message(message, add_all=add_all)
        return ok

    def commit_with_message(self, message: str, *, add_all: bool = True) -> tuple[bool, str]:
        """Коммит с сообщением."""
        try:
            if add_all:
                self._repo_git().add("-A")
            self._repo_git().commit("-m", message)
            logger.info("Committed: %s", message[:60])
            return True, f"Коммит создан: {message}"
        except Exception as e:
            logger.error("Commit failed: %s", e)
            return False, f"Коммит не удался: {e}"

    def has_upstream(self, branch: str | None = None) -> bool:
        if not self._repo:
            return False
        try:
            repo = self._repo  # type: ignore[assignment]
            if branch:
                for ref in repo.branches:
                    if ref.name == branch and ref.tracking_branch():
                        return True
                return False
            return repo.active_branch.tracking_branch() is not None
        except Exception:
            return False

    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        *,
        set_upstream: bool = False,
    ) -> tuple[bool, str]:
        """git push."""
        branch = branch or self.current_branch()
        try:
            if set_upstream or not self.has_upstream(branch):
                out = self._repo_git().push("-u", remote, branch)
            else:
                out = self._repo_git().push(remote, branch)
            detail = (out or "").strip()
            msg = f"Запушено: {remote}/{branch}"
            if detail:
                msg += f"\n{detail}"
            return True, msg
        except Exception as e:
            logger.error("git push failed: %s", e)
            return False, f"git push не удался: {e}"

    def pull(self, remote: str = "origin", branch: str | None = None) -> tuple[bool, str]:
        """git pull."""
        try:
            if branch:
                out = self._repo_git().pull(remote, branch)
            else:
                out = self._repo_git().pull()
            detail = (out or "").strip()
            msg = "Изменения подтянуты (git pull)"
            if branch:
                msg = f"Подтянуто с {remote}/{branch}"
            if detail:
                msg += f"\n{detail}"
            return True, msg
        except Exception as e:
            logger.error("git pull failed: %s", e)
            return False, f"git pull не удался: {e}"

    def merge(self, branch: str) -> tuple[bool, str]:
        """git merge <branch> в текущую ветку."""
        try:
            out = self._repo_git().merge(branch)
            detail = (out or "").strip()
            msg = f"Ветка {branch} смержена в {self.current_branch()}"
            if detail:
                msg += f"\n{detail}"
            return True, msg
        except Exception as e:
            logger.error("git merge failed: %s", e)
            return False, f"git merge не удался: {e}"

    def current_branch(self) -> str:
        if not self._repo:
            return "unknown"
        try:
            return self._repo.active_branch.name  # type: ignore[union-attr]
        except Exception:
            return "HEAD (detached)"

    def branches(self) -> list[str]:
        if not self._repo:
            return []
        try:
            return [b.name for b in self._repo.branches]  # type: ignore[union-attr]
        except Exception:
            return []

    def get_file_at_head(self, path: str) -> str:
        """Get file content at HEAD."""
        if not self._repo:
            return ""
        try:
            return self._repo_git().show(f"HEAD:{path}")
        except Exception:
            return ""

    def file_diff(self, path: str) -> str:
        """Get diff for a specific file."""
        return self.diff(path=path) or self.diff(staged=True, path=path)
