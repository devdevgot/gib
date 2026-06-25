"""Architect Agent — high-level architecture decisions."""
from __future__ import annotations

from typing import Any

from gib.agents.base import BaseAgent, AgentResult
from gib.prompts import PromptLibrary
from gib.router import ModelRouter, TaskType
from gib.workspace import ProjectProfile


class ArchitectAgent(BaseAgent):
    """Handles architecture analysis and design decisions."""

    name = "architect"

    def __init__(self) -> None:
        super().__init__()
        self._router = ModelRouter()

    async def run(
        self,
        prompt: str,
        profile: ProjectProfile | None = None,
        file_context: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        model = self._router.select_model(TaskType.ARCHITECTURE)
        messages = PromptLibrary.general(
            f"[Architecture task]\n{prompt}", profile, file_context
        )

        try:
            resp = await self._call(messages, model=model, temperature=0.3, max_tokens=8192)
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
                output=f"Агент архитектора завершился с ошибкой: {e}",
            )
