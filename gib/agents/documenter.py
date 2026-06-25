"""Documenter Agent — generates documentation."""
from __future__ import annotations

from typing import Any

from gib.agents.base import BaseAgent, AgentResult
from gib.prompts import PromptLibrary
from gib.router import ModelRouter, TaskType
from gib.workspace import ProjectProfile


class DocumenterAgent(BaseAgent):
    """Generates code documentation."""

    name = "documenter"

    def __init__(self) -> None:
        super().__init__()
        self._router = ModelRouter()

    async def run(
        self,
        code: str,
        path: str = "",
        profile: ProjectProfile | None = None,
        **kwargs: Any,
    ) -> AgentResult:
        model = self._router.select_model(TaskType.DOCS)
        messages = PromptLibrary.docs(code, path, profile)

        try:
            resp = await self._call(messages, model=model, temperature=0.3)
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
                output=f"Documentation failed: {e}",
            )
