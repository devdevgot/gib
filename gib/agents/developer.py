"""Developer Agent — implements features and fixes bugs."""
from __future__ import annotations

from typing import Any

from gib.agents.base import BaseAgent, AgentResult
from gib.prompts import PromptLibrary
from gib.router import ModelRouter, TaskType
from gib.workspace import ProjectProfile


class DeveloperAgent(BaseAgent):
    """Writes and fixes code."""

    name = "developer"

    def __init__(self) -> None:
        super().__init__()
        self._router = ModelRouter()

    async def run(
        self,
        prompt: str,
        task_type: TaskType = TaskType.GENERAL,
        profile: ProjectProfile | None = None,
        file_context: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        model = self._router.select_model(task_type)
        messages = PromptLibrary.general(prompt, profile, file_context)

        try:
            resp = await self._call(messages, model=model)
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=resp.content,
                model=resp.model,
                cost_usd=resp.cost_usd,
                latency_ms=resp.latency_ms,
            )
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                success=False,
                output=f"Developer agent failed: {e}",
            )
