"""Memory Agent — manages long-term memory and context."""
from __future__ import annotations

from typing import Any

from gib.agents.base import BaseAgent, AgentResult
from gib.memory import MemoryStore


class MemoryAgent(BaseAgent):
    """Reads and writes long-term memory."""

    name = "memory_agent"

    def __init__(self, project_root: str = "") -> None:
        super().__init__()
        self._store = MemoryStore(project_root=project_root or None)

    async def run(
        self,
        operation: str = "recent",
        project_path: str = "",
        limit: int = 10,
        **kwargs: Any,
    ) -> AgentResult:
        if operation == "recent":
            tasks = self._store.recent_tasks(limit=limit, project_path=project_path)
            if not tasks:
                return AgentResult(
                    agent_name=self.name,
                    success=True,
                    output="No previous tasks found.",
                )
            lines = []
            for t in tasks:
                lines.append(
                    f"[{t.created_at}] {t.task_type}: {t.prompt[:60]}... "
                    f"(model: {t.model_used}, cost: ${t.cost_usd})"
                )
            return AgentResult(
                agent_name=self.name,
                success=True,
                output="\n".join(lines),
                metadata={"tasks": tasks},
            )

        elif operation == "profile":
            profile = self._store.get_project_profile(project_path)
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=str(profile),
                metadata={"profile": profile},
            )

        return AgentResult(
            agent_name=self.name,
            success=False,
            output=f"Unknown memory operation: {operation}",
        )
