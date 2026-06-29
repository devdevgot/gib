"""Выполнение распознанных git-команд."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gib.git.intent import GitAction, GitIntent
from gib.git.integration import GitIntegration


@dataclass
class GitCommandResult:
    success: bool
    message: str
    detail: str = ""


def execute_git_intent(
    intent: GitIntent,
    repo_path: Path | None = None,
) -> GitCommandResult:
    """Выполняет git-команду по намерению."""
    git = GitIntegration(repo_path)

    if not git.is_git_repo:
        return GitCommandResult(
            success=False,
            message="Это не git-репозиторий. Выполните git init или перейдите в клон проекта.",
        )

    if intent.action == GitAction.STATUS:
        ok, msg = git.status_summary()
        return GitCommandResult(success=ok, message=msg)

    if intent.action == GitAction.ADD:
        ok, msg = git.add(paths=intent.paths)
        return GitCommandResult(success=ok, message=msg)

    if intent.action == GitAction.PUSH:
        ok, msg = git.push(
            remote=intent.remote,
            branch=intent.branch,
            set_upstream=intent.set_upstream,
        )
        return GitCommandResult(success=ok, message=msg)

    if intent.action == GitAction.PULL:
        ok, msg = git.pull(remote=intent.remote, branch=intent.branch)
        return GitCommandResult(success=ok, message=msg)

    if intent.action == GitAction.MERGE:
        if not intent.branch:
            return GitCommandResult(success=False, message="Укажите ветку, например: мержни main")
        ok, msg = git.merge(intent.branch)
        return GitCommandResult(success=ok, message=msg)

    if intent.action == GitAction.COMMIT:
        if intent.commit_message:
            ok, msg = git.commit_with_message(intent.commit_message)
            return GitCommandResult(success=ok, message=msg)
        return GitCommandResult(
            success=False,
            message="Для коммита с AI используйте: gib commit",
            detail="commit_ai",
        )

    return GitCommandResult(success=False, message=f"Неизвестная git-операция: {intent.action}")
