"""Core Orchestrator — единая точка входа для всех AI задач.

Делегирует выполнение WorkflowRegistry.
Сохраняет обратную совместимость с CLI командами.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gib.config import get_config
from gib.core.state import GibState, make_initial_state
from gib.core.types import WorkflowType
from gib.graph.registry import WorkflowRegistry
from gib.memory import MemoryStore
from gib.router import ModelRouter, TaskType
from gib.utils import get_logger
from gib.workspace import ProjectProfile

logger = get_logger("gib.orchestrator")


@dataclass
class PipelineStep:
    """Один шаг пайплайна — для отображения в UI."""
    step: int
    agent_name: str
    model: str
    output: str
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class OrchestratorResult:
    """Результат выполнения workflow."""
    task_type: str
    success: bool
    primary_output: str
    pipeline_steps: list[PipelineStep] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    model_used: str = ""
    project_profile: ProjectProfile | None = None
    agent_results: list = field(default_factory=list)  # legacy compat
    metadata: dict[str, Any] = field(default_factory=dict)

    def cost_str(self) -> str:
        if self.total_cost_usd < 0.001:
            return f"${self.total_cost_usd * 1000:.4f}m"
        return f"${self.total_cost_usd:.4f}"

    @property
    def is_pipeline(self) -> bool:
        return len(self.pipeline_steps) > 1


def _state_to_result(
    final_state: GibState,
    task_type: str,
    elapsed_ms: int,
    profile: ProjectProfile | None,
) -> OrchestratorResult:
    """Конвертирует финальный GibState в OrchestratorResult для CLI."""
    models_used: list[str] = final_state.get("models_used", [])
    total_cost: float = final_state.get("total_cost_usd", 0.0)

    # Финальный вывод: review_result → code_result → final_output
    primary = (
        final_state.get("final_output")
        or final_state.get("review_result")
        or final_state.get("code_result")
        or final_state.get("research_result")
        or ""
    )

    # Собираем шаги пайплайна из agent_outputs
    steps: list[PipelineStep] = []
    for i, output in enumerate(final_state.get("agent_outputs", [])):
        steps.append(PipelineStep(
            step=i + 1,
            agent_name=output.role.value if hasattr(output.role, "value") else str(output.role),
            model=output.model_id,
            output=output.content[:200],
            cost_usd=output.cost_usd,
            latency_ms=output.latency_ms,
        ))

    # Если нет agent_outputs — строим из models_used
    if not steps:
        agent_names = ["Аналитик", "Архитектор", "Разработчик", "Ревьюер", "Исследователь"]
        for i, model in enumerate(models_used):
            steps.append(PipelineStep(
                step=i + 1,
                agent_name=agent_names[i % len(agent_names)],
                model=model,
                output="",
                cost_usd=0.0,
                latency_ms=0,
            ))

    return OrchestratorResult(
        task_type=task_type,
        success=final_state.get("success", False),
        primary_output=primary,
        pipeline_steps=steps,
        total_cost_usd=total_cost,
        total_latency_ms=elapsed_ms,
        model_used=models_used[-1] if models_used else "",
        project_profile=profile,
        metadata=final_state.get("metadata", {}),
    )


class Orchestrator:
    """
    Центральный координатор GIB.
    
    Делегирует все AI задачи в соответствующие workflow через WorkflowRegistry.
    Управляет кешем профиля проекта и персистентностью задач.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()
        self._config = get_config()
        self._router = ModelRouter()
        self._memory = MemoryStore()
        self._profile: ProjectProfile | None = None

    async def _get_profile(self) -> ProjectProfile | None:
        """Ленивый анализ профиля проекта."""
        if self._profile:
            return self._profile

        # Пробуем из памяти
        cached = self._memory.get_project_profile(str(self.root))
        if cached:
            try:
                self._profile = ProjectProfile(**cached)
                return self._profile
            except Exception:
                pass

        # Запускаем анализатор
        from gib.agents import ProjectAnalyzerAgent
        agent = ProjectAnalyzerAgent()
        result = await agent.run(root=self.root)
        profile = result.metadata.get("profile")
        if profile:
            self._profile = profile
            self._memory.save_project_profile(str(self.root), profile.model_dump())
        return self._profile

    async def _run_workflow(
        self,
        workflow_type: WorkflowType,
        user_request: str,
        target_paths: list[str] | None = None,
        error_input: str = "",
    ) -> tuple[GibState, ProjectProfile | None]:
        """Запускает workflow и возвращает финальное состояние."""
        profile = await self._get_profile()

        initial = make_initial_state(
            user_request=user_request,
            workflow_type=workflow_type.value,
            target_paths=target_paths or [],
            error_input=error_input,
        )

        final_state = await WorkflowRegistry.run(workflow_type, initial)
        return final_state, profile

    def _persist(
        self,
        task_type: str,
        prompt: str,
        final_state: GibState,
    ) -> None:
        """Сохраняет задачу в долговременную память."""
        models = final_state.get("models_used", [])
        self._memory.save_task(
            task_type=task_type,
            prompt=prompt,
            model_used=" → ".join(models[-5:]),
            result_summary=(
                final_state.get("final_output")
                or final_state.get("review_result")
                or ""
            )[:500],
            cost_usd=final_state.get("total_cost_usd", 0.0),
            project_path=str(self.root),
            status="completed" if final_state.get("success") else "failed",
        )

    # ── Public API (совместим с CLI командами) ───────────────────────────────

    async def run_general(self, prompt: str) -> OrchestratorResult:
        """gib ask — Feature workflow."""
        start = time.monotonic()
        final_state, profile = await self._run_workflow(
            WorkflowType.FEATURE, prompt
        )
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.GENERAL), prompt, final_state)
        return _state_to_result(final_state, str(TaskType.GENERAL), elapsed, profile)

    async def run_fix(
        self,
        paths: list[Path] | None = None,
        error: str = "",
        review_context: str = "",
    ) -> OrchestratorResult:
        """gib fix — BugFix workflow."""
        start = time.monotonic()
        path_strs = [str(p) for p in paths] if paths else []

        # Если есть результат ревью — вставляем его как контекст задачи,
        # чтобы агент точно знал что исправлять
        user_request = "Исправить баги в коде"
        if review_context:
            user_request = (
                "Исправить все проблемы, найденные в ходе code review.\n\n"
                f"Результаты ревью:\n{review_context}"
            )
        elif error:
            user_request = f"Исправить баги в коде. Ошибка: {error}"

        final_state, profile = await self._run_workflow(
            WorkflowType.BUGFIX,
            user_request,
            target_paths=path_strs,
            error_input=error,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.FIX), "fix code", final_state)
        return _state_to_result(final_state, str(TaskType.FIX), elapsed, profile)

    async def run_refactor(self, paths: list[Path]) -> OrchestratorResult:
        """gib refactor — Refactor workflow."""
        start = time.monotonic()
        path_strs = [str(p) for p in paths]
        path_str = ", ".join(path_strs)
        final_state, profile = await self._run_workflow(
            WorkflowType.REFACTOR,
            f"Рефакторинг файлов: {path_str}",
            target_paths=path_strs,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.REFACTOR), f"refactor {path_str}", final_state)
        return _state_to_result(final_state, str(TaskType.REFACTOR), elapsed, profile)

    async def run_review(
        self,
        paths: list[Path] | None = None,
    ) -> OrchestratorResult:
        """gib review — Review workflow."""
        start = time.monotonic()
        path_strs = [str(p) for p in paths] if paths else []
        final_state, profile = await self._run_workflow(
            WorkflowType.REVIEW,
            "Провести code review",
            target_paths=path_strs,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.REVIEW), "code review", final_state)
        return _state_to_result(final_state, str(TaskType.REVIEW), elapsed, profile)

    async def run_explain(self, path: Path) -> OrchestratorResult:
        """gib explain — Explain workflow."""
        start = time.monotonic()
        final_state, profile = await self._run_workflow(
            WorkflowType.EXPLAIN,
            f"Объясни код в {path}",
            target_paths=[str(path)],
        )
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.EXPLAIN), f"explain {path}", final_state)
        return _state_to_result(final_state, str(TaskType.EXPLAIN), elapsed, profile)

    async def run_doctor(self) -> OrchestratorResult:
        """gib doctor — Doctor workflow."""
        start = time.monotonic()
        final_state, profile = await self._run_workflow(
            WorkflowType.DOCTOR,
            "Полная диагностика проекта",
        )
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.DOCTOR), "doctor", final_state)
        return _state_to_result(final_state, str(TaskType.DOCTOR), elapsed, profile)

    async def run_test(self, paths: list[Path] | None = None) -> OrchestratorResult:
        """gib test — использует Feature workflow с акцентом на тесты."""
        start = time.monotonic()
        path_strs = [str(p) for p in paths] if paths else []
        # Запускаем feature workflow с модифицированным запросом
        initial = make_initial_state(
            user_request="Написать тесты для кода",
            workflow_type=WorkflowType.FEATURE.value,
            target_paths=path_strs,
        )
        final_state = await WorkflowRegistry.run(WorkflowType.FEATURE, initial)
        profile = await self._get_profile()
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.TEST), "generate tests", final_state)
        return _state_to_result(final_state, str(TaskType.TEST), elapsed, profile)

    async def run_docs(self, paths: list[Path] | None = None) -> OrchestratorResult:
        """gib docs — Feature workflow с акцентом на документацию."""
        start = time.monotonic()
        path_strs = [str(p) for p in paths] if paths else []
        initial = make_initial_state(
            user_request="Написать документацию для кода",
            workflow_type=WorkflowType.FEATURE.value,
            target_paths=path_strs,
        )
        final_state = await WorkflowRegistry.run(WorkflowType.FEATURE, initial)
        profile = await self._get_profile()
        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(str(TaskType.DOCS), "generate docs", final_state)
        return _state_to_result(final_state, str(TaskType.DOCS), elapsed, profile)

    async def run_commit(self) -> OrchestratorResult:
        """gib commit — генерирует сообщение коммита (без workflow, прямой вызов)."""
        start = time.monotonic()

        from gib.agents import GitAgent
        agent = GitAgent()
        result = await agent.run(operation="commit_message", repo_path=self.root)

        elapsed = int((time.monotonic() - start) * 1000)

        return OrchestratorResult(
            task_type=str(TaskType.COMMIT),
            success=result.success,
            primary_output=result.output,
            total_cost_usd=result.cost_usd,
            total_latency_ms=elapsed,
            model_used=result.model,
            metadata=result.metadata,
        )

    @property
    def metadata(self) -> dict[str, Any]:
        return {}
