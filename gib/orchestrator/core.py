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
class OrchestratorResult:
    task_type: str
    success: bool
    primary_output: str
    agent_results: list[AgentResult] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    model_used: str = ""
    project_profile: ProjectProfile | None = None

    def cost_str(self) -> str:
        if self.total_cost_usd < 0.001:
            return f"${self.total_cost_usd * 1000:.4f}m"
        return f"${self.total_cost_usd:.4f}"


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
        """Handle a free-form user prompt."""
        start = time.monotonic()
        profile = await self._analyze_project()
        task_type, model = self._router.route(prompt)

        agent = DeveloperAgent()
        result = await agent.run(
            prompt=prompt,
            task_type=task_type,
            profile=profile,
        )

        elapsed = int((time.monotonic() - start) * 1000)
        self._memory.save_task(
            task_type=str(task_type),
            prompt=prompt,
            model_used=result.model,
            result_summary=result.output[:500],
            cost_usd=result.cost_usd,
            project_path=str(self.root),
            status="completed" if result.success else "failed",
        )

        return OrchestratorResult(
            task_type=str(task_type),
            success=result.success,
            primary_output=result.output,
            agent_results=[result],
            total_cost_usd=result.cost_usd,
            total_latency_ms=elapsed,
            model_used=result.model,
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
        """Fix bugs in provided files."""
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

        from gib.prompts import PromptLibrary
        messages = PromptLibrary.fix(code, error=error, project=profile)

        from gib.providers import ChatMessage, OpenRouterClient
        client = OpenRouterClient()
        model = self._router.select_model(TaskType.FIX)
        resp = await client.chat([ChatMessage(**m) for m in messages], model=model)
        result = AgentResult(
            agent_name="developer",
            success=True,
            output=resp.content,
            model=resp.model,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
        )

        elapsed = int((time.monotonic() - start) * 1000)
        self._persist(TaskType.FIX, "fix code", result)

        return OrchestratorResult(
            task_type=TaskType.FIX,
            success=True,
            primary_output=result.output,
            agent_results=[result],
            total_cost_usd=result.cost_usd,
            total_latency_ms=elapsed,
            model_used=result.model,
            project_profile=profile,
        )

    async def run_refactor(self, paths: list[Path]) -> OrchestratorResult:
        """Refactor code in provided paths."""
        start = time.monotonic()
        profile = await self._analyze_project()
        code = self._collect_file_context(paths)

        if not code:
            return OrchestratorResult(
                task_type=TaskType.REFACTOR,
                success=False,
                primary_output="Нет кода для рефакторинга. Укажите пути к файлам или директориям.",
            )

        from gib.providers import ChatMessage, OpenRouterClient
        from gib.prompts import PromptLibrary
        client = OpenRouterClient()
        model = self._router.select_model(TaskType.REFACTOR)
        path_str = ", ".join(str(p) for p in paths)
        msgs = PromptLibrary.refactor(code, path=path_str, project=profile)
        resp = await client.chat([ChatMessage(**m) for m in msgs], model=model)

        elapsed = int((time.monotonic() - start) * 1000)
        result = AgentResult(
            agent_name="developer",
            success=True,
            output=resp.content,
            model=resp.model,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
        )
        self._persist(TaskType.REFACTOR, f"refactor {path_str}", result)

        return OrchestratorResult(
            task_type=TaskType.REFACTOR,
            success=True,
            primary_output=resp.content,
            agent_results=[result],
            total_cost_usd=resp.cost_usd,
            total_latency_ms=elapsed,
            model_used=resp.model,
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
