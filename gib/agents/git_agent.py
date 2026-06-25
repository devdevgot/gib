"""Git Agent — handles git operations and commit message generation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from gib.agents.base import BaseAgent, AgentResult
from gib.git import GitIntegration
from gib.prompts import PromptLibrary
from gib.router import ModelRouter, TaskType


class GitAgent(BaseAgent):
    """Manages git operations and generates commit messages."""

    name = "git_agent"

    def __init__(self) -> None:
        super().__init__()
        self._router = ModelRouter()

    async def run(
        self,
        operation: str = "commit_message",
        repo_path: Path | None = None,
        commit_message: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        git = GitIntegration(repo_path)

        if operation == "commit_message":
            diff = git.full_diff()
            if not diff:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output="No changes to commit (empty diff)",
                )
            model = self._router.select_model(TaskType.COMMIT)
            messages = PromptLibrary.commit_message(diff[:8000])
            try:
                resp = await self._call(messages, model=model, temperature=0.1, max_tokens=512)
                return AgentResult(
                    agent_name=self.name,
                    success=True,
                    output=resp.content.strip(),
                    model=resp.model,
                    cost_usd=resp.cost_usd,
                    latency_ms=resp.latency_ms,
                    metadata={"diff": diff, "git": git},
                )
            except Exception as e:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output=f"Commit message generation failed: {e}",
                )

        elif operation == "do_commit":
            if not commit_message:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output="No commit message provided",
                )
            success = git.commit(commit_message)
            return AgentResult(
                agent_name=self.name,
                success=success,
                output=f"Committed: {commit_message}" if success else "Commit failed",
            )

        elif operation == "status":
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=git.status(),
            )

        elif operation == "diff":
            diff = git.full_diff()
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=diff or "No changes",
            )

        return AgentResult(
            agent_name=self.name,
            success=False,
            output=f"Unknown git operation: {operation}",
        )
