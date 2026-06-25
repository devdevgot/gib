"""Core Orchestrator — coordinates agents, manages task lifecycle."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gib.agents import (
    AgentResult,
    ArchitectAgent,
    DeveloperAgent,
    DocumenterAgent,
    GitAgent,
    MemoryAgent,
    ProjectAnalyzerAgent,
    ReviewerAgent,
    TesterAgent,
)
from gib.config import get_config
from gib.memory import MemoryStore
from gib.router import ModelRouter, TaskType
from gib.utils import get_logger
from gib.workspace import ProjectProfile

logger = get_logger("gib.orchestrator")


@dataclass
class PipelineStep:
    """Один шаг пайплайна — результат одного агента."""
    step: int
    agent_name: str
    model: str
    output: str
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class OrchestratorResult:
    task_type: str
    success: bool
    primary_output: str
    agent_results: list[AgentResult] = field(default_factory=list)
    pipeline_steps: list[PipelineStep] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    model_used: str = ""
    project_profile: ProjectProfile | None = None

    def cost_str(self) -> str:
        if self.total_cost_usd < 0.001:
            return f"${self.total_cost_usd * 1000:.4f}m"
        return f"${self.total_cost_usd:.4f}"

    @property
    def is_pipeline(self) -> bool:
        return len(self.pipeline_steps) > 1


def _build_pipeline_steps(final_state: dict) -> list[PipelineStep]:
    """Собирает список PipelineStep из финального состояния LangGraph."""
    models_used: list[str] = final_state.get("models_used", [])
    steps: list[PipelineStep] = []

    # Имена агентов по порядку появления в пайплайне
    agent_names = {
        0: "Архитектор",
        1: "Разработчик",
        2: "Ревьюер",
    }
    # fix pipeline: только developer + reviewer (2 модели)
    if len(models_used) <= 2:
        agent_names = {0: "Разработчик", 1: "Ревьюер"}

    for i, model in enumerate(models_used):
        steps.append(PipelineStep(
            step=i + 1,
            agent_name=agent_names.get(i % len(agent_names), f"Агент {i + 1}"),
            model=model,
            output="",  # детальный output не хранится в финальном state
            cost_usd=0.0,
            latency_ms=0,
        ))

    return steps


class Orchestrator:
    """
    Central coordinator that:
    1. Analyzes the project
    2. Routes the task to the right model
    3. Spins up agents (in parallel where possible)
    4. Combines results
    5. Persists to memory
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()
        self._config = get_config()
        self._router = ModelRouter()
        self._memory = MemoryStore()
        self._profile: ProjectProfile | None = None

    async def _analyze_project(self) -> ProjectProfile:
        """Run project analysis and cache result."""
        if self._profile:
            return self._profile
        agent = ProjectAnalyzerAgent()
        result = await agent.run(root=self.root)
        profile = result.metadata.get("profile")
        if profile:
            self._profile = profile
            self._memory.save_project_profile(str(self.root), profile.model_dump())
        return profile

    def _collect_file_context(self, paths: list[Path], max_chars: int = 20000) -> str:
        """Read and concatenate file contents for context."""
        parts: list[str] = []
        total = 0
        for p in paths:
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(errors="ignore")
                    chunk = f"# {p}\n{content}\n"
                    if total + len(chunk) > max_chars:
                        break
                    parts.append(chunk)
                    total += len(chunk)
                except Exception:
                    continue
        return "\n".join(parts)

    async def run_general(self, prompt: str) -> OrchestratorResult:
        """
        LangGraph пайплайн: Claude → GPT-5.5 → Gemini (с авто-retry если ревью не пройдено).
        """
        from gib.pipeline import get_general_graph

        start = time.monotonic()
        profile = await self._analyze_project()
        file_context = self._collect_source_context(max_chars=15000)

        initial_state = {
            "prompt": prompt,
            "file_context": file_context,
            "error_context": "",
            "project_meta": profile.model_dump() if profile else {},
            "architect_plan": "",
            "developer_code": "",
            "review_result": "",
            "review_verdict": "",
            "iteration": 1,
            "max_iterations": 2,
            "total_cost_usd": 0.0,
            "total_latency_ms": 0,
            "models_used": [],
            "final_output": "",
            "success": False,
        }

        graph = get_general_graph()
        final_state = await graph.ainvoke(initial_state)

        elapsed = int((time.monotonic() - start) * 1000)
        models_used = final_state.get("models_used", [])
        total_cost = final_state.get("total_cost_usd", 0.0)

        self._memory.save_task(
            task_type=str(TaskType.GENERAL),
            prompt=prompt,
            model_used=" → ".join(models_used),
            result_summary=final_state.get("final_output", "")[:500],
            cost_usd=total_cost,
            project_path=str(self.root),
            status="completed" if final_state.get("success") else "failed",
        )

        # Собираем pipeline_steps из финального состояния для UI
        steps = _build_pipeline_steps(final_state)

        return OrchestratorResult(
            task_type=str(TaskType.GENERAL),
            success=final_state.get("success", False),
            primary_output=final_state.get("final_output", ""),
            pipeline_steps=steps,
            total_cost_usd=total_cost,
            total_latency_ms=elapsed,
            model_used=models_used[-1] if models_used else "",
            project_profile=profile,
        )

    async def run_review(self, paths: list[Path] | None = None) -> OrchestratorResult:
        """Run code review on provided paths or changed files."""
        start = time.monotonic()
        profile = await self._analyze_project()

        # Collect code to review
        if paths:
            code = self._collect_file_context(paths)
        else:
            # Review all source files
            code = self._collect_source_context(max_chars=30000)

        if not code:
            return OrchestratorResult(
                task_type=TaskType.REVIEW,
                success=False,
                primary_output="Нет кода для ревью. Укажите файлы или запустите из директории проекта.",
            )

        agent = ReviewerAgent()
        result = await agent.run(code=code, profile=profile)

        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(TaskType.REVIEW, "code review", result)

        return OrchestratorResult(
            task_type=TaskType.REVIEW,
            success=result.success,
            primary_output=result.output,
            agent_results=[result],
            total_cost_usd=result.cost_usd,
            total_latency_ms=elapsed,
            model_used=result.model,
            project_profile=profile,
        )

    async def run_fix(self, paths: list[Path] | None = None, error: str = "") -> OrchestratorResult:
        """
        LangGraph fix пайплайн: GPT-5.5 → Gemini (с авто-retry если ревью не пройдено).
        """
        from gib.pipeline import get_fix_graph

        start = time.monotonic()
        profile = await self._analyze_project()

        if paths:
            code = self._collect_file_context(paths)
        else:
            code = self._collect_source_context(max_chars=20000)

        if not code:
            return OrchestratorResult(
                task_type=TaskType.FIX,
                success=False,
                primary_output="Нет кода для исправления. Укажите пути к файлам.",
            )

        initial_state = {
            "prompt": "Исправить баги в коде",
            "file_context": code,
            "error_context": error,
            "project_meta": profile.model_dump() if profile else {},
            "architect_plan": "",
            "developer_code": "",
            "review_result": "",
            "review_verdict": "",
            "iteration": 1,
            "max_iterations": 2,
            "total_cost_usd": 0.0,
            "total_latency_ms": 0,
            "models_used": [],
            "final_output": "",
            "success": False,
        }

        graph = get_fix_graph()
        final_state = await graph.ainvoke(initial_state)

        elapsed = int((time.monotonic() - start) * 1000)
        models_used = final_state.get("models_used", [])
        total_cost = final_state.get("total_cost_usd", 0.0)

        self._memory.save_task(
            task_type=str(TaskType.FIX),
            prompt="fix code",
            model_used=" → ".join(models_used),
            result_summary=final_state.get("final_output", "")[:500],
            cost_usd=total_cost,
            project_path=str(self.root),
            status="completed" if final_state.get("success") else "failed",
        )

        steps = _build_pipeline_steps(final_state)

        return OrchestratorResult(
            task_type=TaskType.FIX,
            success=final_state.get("success", False),
            primary_output=final_state.get("final_output", ""),
            pipeline_steps=steps,
            total_cost_usd=total_cost,
            total_latency_ms=elapsed,
            model_used=models_used[-1] if models_used else "",
            project_profile=profile,
        )

    async def run_refactor(self, paths: list[Path]) -> OrchestratorResult:
        """
        LangGraph refactor пайплайн: Claude → GPT-5.5 → Gemini (с авто-retry если ревью не пройдено).
        """
        from gib.pipeline import get_general_graph

        start = time.monotonic()
        profile = await self._analyze_project()

        code = self._collect_file_context(paths)
        path_str = ", ".join(str(p) for p in paths)

        if not code:
            return OrchestratorResult(
                task_type=TaskType.REFACTOR,
                success=False,
                primary_output="Нет кода для рефакторинга. Укажите пути к файлам или директориям.",
            )

        initial_state = {
            "prompt": f"Рефакторинг файлов: {path_str}",
            "file_context": code,
            "error_context": "",
            "project_meta": profile.model_dump() if profile else {},
            "architect_plan": "",
            "developer_code": "",
            "review_result": "",
            "review_verdict": "",
            "iteration": 1,
            "max_iterations": 2,
            "total_cost_usd": 0.0,
            "total_latency_ms": 0,
            "models_used": [],
            "final_output": "",
            "success": False,
        }

        graph = get_general_graph()
        final_state = await graph.ainvoke(initial_state)

        elapsed = int((time.monotonic() - start) * 1000)
        models_used = final_state.get("models_used", [])
        total_cost = final_state.get("total_cost_usd", 0.0)

        self._memory.save_task(
            task_type=str(TaskType.REFACTOR),
            prompt=f"refactor {path_str}",
            model_used=" → ".join(models_used),
            result_summary=final_state.get("final_output", "")[:500],
            cost_usd=total_cost,
            project_path=str(self.root),
            status="completed" if final_state.get("success") else "failed",
        )

        steps = _build_pipeline_steps(final_state)

        return OrchestratorResult(
            task_type=TaskType.REFACTOR,
            success=final_state.get("success", False),
            primary_output=final_state.get("final_output", ""),
            pipeline_steps=steps,
            total_cost_usd=total_cost,
            total_latency_ms=elapsed,
            model_used=models_used[-1] if models_used else "",
            project_profile=profile,
        )

    async def run_test(self, paths: list[Path] | None = None) -> OrchestratorResult:
        """Generate tests for code."""
        start = time.monotonic()
        profile = await self._analyze_project()

        if paths:
            code = self._collect_file_context(paths)
        else:
            code = self._collect_source_context(max_chars=20000)

        if not code:
            return OrchestratorResult(
                task_type=TaskType.TEST,
                success=False,
                primary_output="Нет кода для тестирования. Укажите пути к файлам.",
            )

        # Detect test framework
        fw_map = {
            "Python": "pytest",
            "JavaScript": "jest",
            "TypeScript": "jest",
            "Go": "testing",
            "Java": "JUnit",
            "Rust": "cargo test",
        }
        test_framework = fw_map.get(profile.language, "") if profile else ""

        agent = TesterAgent()
        result = await agent.run(code=code, profile=profile, test_framework=test_framework)

        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(TaskType.TEST, "generate tests", result)

        return OrchestratorResult(
            task_type=TaskType.TEST,
            success=result.success,
            primary_output=result.output,
            agent_results=[result],
            total_cost_usd=result.cost_usd,
            total_latency_ms=elapsed,
            model_used=result.model,
            project_profile=profile,
        )

    async def run_docs(self, paths: list[Path] | None = None) -> OrchestratorResult:
        """Generate documentation."""
        start = time.monotonic()
        profile = await self._analyze_project()

        if paths:
            code = self._collect_file_context(paths)
            path_str = ", ".join(str(p) for p in paths)
        else:
            code = self._collect_source_context(max_chars=20000)
            path_str = str(self.root)

        if not code:
            return OrchestratorResult(
                task_type=TaskType.DOCS,
                success=False,
                primary_output="Нет кода для документирования.",
            )

        agent = DocumenterAgent()
        result = await agent.run(code=code, path=path_str, profile=profile)

        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(TaskType.DOCS, "generate docs", result)

        return OrchestratorResult(
            task_type=TaskType.DOCS,
            success=result.success,
            primary_output=result.output,
            agent_results=[result],
            total_cost_usd=result.cost_usd,
            total_latency_ms=elapsed,
            model_used=result.model,
            project_profile=profile,
        )

    async def run_commit(self) -> OrchestratorResult:
        """Generate and create a git commit."""
        start = time.monotonic()
        agent = GitAgent()
        result = await agent.run(operation="commit_message", repo_path=self.root)

        elapsed = int((time.monotonic() - start) * 1000)

        return OrchestratorResult(
            task_type=TaskType.COMMIT,
            success=result.success,
            primary_output=result.output,
            agent_results=[result],
            total_cost_usd=result.cost_usd,
            total_latency_ms=elapsed,
            model_used=result.model,
            metadata=result.metadata,
        )

    async def run_doctor(self) -> OrchestratorResult:
        """Run full project diagnostics."""
        start = time.monotonic()
        profile = await self._analyze_project()
        code = self._collect_source_context(max_chars=40000)

        from gib.providers import ChatMessage, OpenRouterClient
        from gib.prompts import PromptLibrary
        client = OpenRouterClient()
        model = self._router.select_model(TaskType.DOCTOR)
        msgs = PromptLibrary.doctor(code or "Исходный код не найден", profile)
        resp = await client.chat([ChatMessage(**m) for m in msgs], model=model, max_tokens=8192)

        result = AgentResult(
            agent_name="reviewer",
            success=True,
            output=resp.content,
            model=resp.model,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
        )

        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(TaskType.DOCTOR, "doctor", result)

        return OrchestratorResult(
            task_type=TaskType.DOCTOR,
            success=True,
            primary_output=resp.content,
            agent_results=[result],
            total_cost_usd=resp.cost_usd,
            total_latency_ms=elapsed,
            model_used=resp.model,
            project_profile=profile,
        )

    async def run_explain(self, path: Path) -> OrchestratorResult:
        """Explain a specific file or directory."""
        start = time.monotonic()
        profile = await self._analyze_project()

        if path.is_file():
            code = self._collect_file_context([path])
            path_str = str(path)
        elif path.is_dir():
            files = list(path.rglob("*.py")) + list(path.rglob("*.ts")) + \
                    list(path.rglob("*.js")) + list(path.rglob("*.go"))
            code = self._collect_file_context(files[:10])
            path_str = str(path)
        else:
            return OrchestratorResult(
                task_type=TaskType.EXPLAIN,
                success=False,
                primary_output=f"Путь не найден: {path}",
            )

        from gib.providers import ChatMessage, OpenRouterClient
        from gib.prompts import PromptLibrary
        client = OpenRouterClient()
        model = self._router.select_model(TaskType.EXPLAIN)
        msgs = PromptLibrary.explain(code, path=path_str, project=profile)
        resp = await client.chat([ChatMessage(**m) for m in msgs], model=model, max_tokens=8192)

        result = AgentResult(
            agent_name="developer",
            success=True,
            output=resp.content,
            model=resp.model,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
        )

        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(TaskType.EXPLAIN, f"explain {path_str}", result)

        return OrchestratorResult(
            task_type=TaskType.EXPLAIN,
            success=True,
            primary_output=resp.content,
            agent_results=[result],
            total_cost_usd=resp.cost_usd,
            total_latency_ms=elapsed,
            model_used=resp.model,
            project_profile=profile,
        )

    def _collect_source_context(self, max_chars: int = 20000) -> str:
        """Collect source files from the project root."""
        extensions = {
            ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs",
            ".java", ".cs", ".rb", ".php", ".cpp", ".c", ".h",
        }
        ignore_dirs = {
            "node_modules", "__pycache__", ".git", "dist", "build",
            ".venv", "venv", "env", ".env", "coverage", ".mypy_cache",
        }
        files: list[Path] = []
        for p in self.root.rglob("*"):
            if any(part in ignore_dirs for part in p.parts):
                continue
            if p.is_file() and p.suffix in extensions:
                files.append(p)

        # Prioritize smaller files, sort by size
        files.sort(key=lambda f: f.stat().st_size)
        return self._collect_file_context(files[:30], max_chars=max_chars)

    def _persist(self, task_type: TaskType, prompt: str, result: AgentResult) -> None:
        self._memory.save_task(
            task_type=str(task_type),
            prompt=prompt,
            model_used=result.model,
            result_summary=result.output[:500],
            cost_usd=result.cost_usd,
            project_path=str(self.root),
            status="completed" if result.success else "failed",
        )

    @property
    def metadata(self) -> dict[str, Any]:
        return {}
