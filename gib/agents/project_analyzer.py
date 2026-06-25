"""Project Analyzer Agent — analyzes the project structure."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from gib.agents.base import BaseAgent, AgentResult
from gib.router import ModelRouter, TaskType
from gib.workspace import ProjectAnalyzer, ProjectProfile


class ProjectAnalyzerAgent(BaseAgent):
    """Detects language, framework, structure and builds project context."""

    name = "project_analyzer"

    def __init__(self) -> None:
        super().__init__()
        self._router = ModelRouter()

    async def run(self, root: Path | None = None, **kwargs: Any) -> AgentResult:
        analyzer = ProjectAnalyzer(root)
        try:
            profile = analyzer.analyze()
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=profile.summary(),
                metadata={"profile": profile},
            )
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                success=False,
                output=f"Analysis failed: {e}",
            )
