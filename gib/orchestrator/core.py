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
        Пайплайн: Claude (архитектор) → GPT-5.5 (разработчик) → Gemini (ревьюер).
        """
        from gib.prompts import PromptLibrary
        from gib.providers import ChatMessage, OpenRouterClient

        start = time.monotonic()
        profile = await self._analyze_project()
        client = OpenRouterClient()
        pipeline_steps: list[PipelineStep] = []
        total_cost = 0.0

        file_context = self._collect_source_context(max_chars=15000)

        # ── Шаг 1: Claude — анализ и план ────────────────────────────────
        logger.info("Pipeline шаг 1/3: Claude (архитектор) анализирует задачу")
        arch_model = self._router.select_model(TaskType.ARCHITECTURE)
        arch_msgs = PromptLibrary.pipeline_architect(prompt, file_context, profile)
        arch_resp = await client.chat(
            [ChatMessage(**m) for m in arch_msgs],
            model=arch_model,
            temperature=0.3,
            max_tokens=4096,
        )
        total_cost += arch_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=1,
            agent_name="Архитектор",
            model=arch_resp.model,
            output=arch_resp.content,
            cost_usd=arch_resp.cost_usd,
            latency_ms=arch_resp.latency_ms,
        ))

        # ── Шаг 2: GPT-5.5 — реализация по плану ─────────────────────────
        logger.info("Pipeline шаг 2/3: GPT-5.5 (разработчик) реализует код")
        dev_model = self._router.select_model(TaskType.FIX)  # GPT-5.5
        dev_msgs = PromptLibrary.pipeline_developer(
            prompt, arch_resp.content, file_context, profile
        )
        dev_resp = await client.chat(
            [ChatMessage(**m) for m in dev_msgs],
            model=dev_model,
            temperature=0.2,
            max_tokens=8192,
        )
        total_cost += dev_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=2,
            agent_name="Разработчик",
            model=dev_resp.model,
            output=dev_resp.content,
            cost_usd=dev_resp.cost_usd,
            latency_ms=dev_resp.latency_ms,
        ))

        # ── Шаг 3: Gemini — ревью кода ────────────────────────────────────
        logger.info("Pipeline шаг 3/3: Gemini (ревьюер) проверяет код")
        rev_model = self._router.select_model(TaskType.REVIEW)  # Gemini 2.5 Pro
        rev_msgs = PromptLibrary.pipeline_reviewer(
            prompt, arch_resp.content, dev_resp.content, profile
        )
        rev_resp = await client.chat(
            [ChatMessage(**m) for m in rev_msgs],
            model=rev_model,
            temperature=0.2,
            max_tokens=8192,
        )
        total_cost += rev_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=3,
            agent_name="Ревьюер",
            model=rev_resp.model,
            output=rev_resp.content,
            cost_usd=rev_resp.cost_usd,
            latency_ms=rev_resp.latency_ms,
        ))

        elapsed = int((time.monotonic() - start) * 1000)
        self._memory.save_task(
            task_type=str(TaskType.GENERAL),
            prompt=prompt,
            model_used=f"{arch_model} → {dev_model} → {rev_model}",
            result_summary=rev_resp.content[:500],
            cost_usd=total_cost,
            project_path=str(self.root),
            status="completed",
        )

        return OrchestratorResult(
            task_type=str(TaskType.GENERAL),
            success=True,
            primary_output=rev_resp.content,
            pipeline_steps=pipeline_steps,
            total_cost_usd=total_cost,
            total_latency_ms=elapsed,
            model_used=rev_resp.model,
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
        Пайплайн fix: GPT-5.5 (исправляет баг) → Gemini (проверяет исправление).
        """
        from gib.prompts import PromptLibrary
        from gib.providers import ChatMessage, OpenRouterClient

        start = time.monotonic()
        profile = await self._analyze_project()
        client = OpenRouterClient()
        pipeline_steps: list[PipelineStep] = []
        total_cost = 0.0

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

        # ── Шаг 1: GPT-5.5 — исправляет баг ─────────────────────────────
        logger.info("Pipeline fix шаг 1/2: GPT-5.5 исправляет баг")
        dev_model = self._router.select_model(TaskType.FIX)
        fix_msgs = PromptLibrary.fix(code, error=error, project=profile)
        fix_resp = await client.chat(
            [ChatMessage(**m) for m in fix_msgs],
            model=dev_model,
            temperature=0.1,
            max_tokens=8192,
        )
        total_cost += fix_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=1,
            agent_name="Разработчик",
            model=fix_resp.model,
            output=fix_resp.content,
            cost_usd=fix_resp.cost_usd,
            latency_ms=fix_resp.latency_ms,
        ))

        # ── Шаг 2: Gemini — проверяет исправление ────────────────────────
        logger.info("Pipeline fix шаг 2/2: Gemini проверяет исправление")
        rev_model = self._router.select_model(TaskType.REVIEW)
        rev_msgs = PromptLibrary.pipeline_fix_reviewer(code, fix_resp.content, error, profile)
        rev_resp = await client.chat(
            [ChatMessage(**m) for m in rev_msgs],
            model=rev_model,
            temperature=0.1,
            max_tokens=4096,
        )
        total_cost += rev_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=2,
            agent_name="Ревьюер",
            model=rev_resp.model,
            output=rev_resp.content,
            cost_usd=rev_resp.cost_usd,
            latency_ms=rev_resp.latency_ms,
        ))

        elapsed = int((time.monotonic() - start) * 1000)
        self._memory.save_task(
            task_type=str(TaskType.FIX),
            prompt="fix code",
            model_used=f"{dev_model} → {rev_model}",
            result_summary=rev_resp.content[:500],
            cost_usd=total_cost,
            project_path=str(self.root),
            status="completed",
        )

        return OrchestratorResult(
            task_type=TaskType.FIX,
            success=True,
            primary_output=rev_resp.content,
            pipeline_steps=pipeline_steps,
            total_cost_usd=total_cost,
            total_latency_ms=elapsed,
            model_used=rev_resp.model,
            project_profile=profile,
        )

    async def run_refactor(self, paths: list[Path]) -> OrchestratorResult:
        """
        Пайплайн refactor: Claude (план рефакторинга) → GPT-5.5 (рефакторинг) → Gemini (ревью).
        """
        from gib.prompts import PromptLibrary
        from gib.providers import ChatMessage, OpenRouterClient

        start = time.monotonic()
        profile = await self._analyze_project()
        client = OpenRouterClient()
        pipeline_steps: list[PipelineStep] = []
        total_cost = 0.0

        code = self._collect_file_context(paths)
        path_str = ", ".join(str(p) for p in paths)

        if not code:
            return OrchestratorResult(
                task_type=TaskType.REFACTOR,
                success=False,
                primary_output="Нет кода для рефакторинга. Укажите пути к файлам или директориям.",
            )

        # ── Шаг 1: Claude — план рефакторинга ────────────────────────────
        logger.info("Pipeline refactor шаг 1/3: Claude планирует рефакторинг")
        arch_model = self._router.select_model(TaskType.ARCHITECTURE)
        arch_msgs = PromptLibrary.pipeline_architect(
            f"Рефакторинг файлов: {path_str}", code, profile
        )
        arch_resp = await client.chat(
            [ChatMessage(**m) for m in arch_msgs],
            model=arch_model,
            temperature=0.3,
            max_tokens=4096,
        )
        total_cost += arch_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=1,
            agent_name="Архитектор",
            model=arch_resp.model,
            output=arch_resp.content,
            cost_usd=arch_resp.cost_usd,
            latency_ms=arch_resp.latency_ms,
        ))

        # ── Шаг 2: GPT-5.5 — рефакторинг ─────────────────────────────────
        logger.info("Pipeline refactor шаг 2/3: GPT-5.5 рефакторит код")
        dev_model = self._router.select_model(TaskType.FIX)
        ref_msgs = PromptLibrary.pipeline_developer(
            f"Рефакторинг: {path_str}", arch_resp.content, code, profile
        )
        ref_resp = await client.chat(
            [ChatMessage(**m) for m in ref_msgs],
            model=dev_model,
            temperature=0.2,
            max_tokens=8192,
        )
        total_cost += ref_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=2,
            agent_name="Разработчик",
            model=ref_resp.model,
            output=ref_resp.content,
            cost_usd=ref_resp.cost_usd,
            latency_ms=ref_resp.latency_ms,
        ))

        # ── Шаг 3: Gemini — ревью рефакторинга ───────────────────────────
        logger.info("Pipeline refactor шаг 3/3: Gemini проверяет рефакторинг")
        rev_model = self._router.select_model(TaskType.REVIEW)
        rev_msgs = PromptLibrary.pipeline_reviewer(
            f"Рефакторинг: {path_str}", arch_resp.content, ref_resp.content, profile
        )
        rev_resp = await client.chat(
            [ChatMessage(**m) for m in rev_msgs],
            model=rev_model,
            temperature=0.2,
            max_tokens=8192,
        )
        total_cost += rev_resp.cost_usd
        pipeline_steps.append(PipelineStep(
            step=3,
            agent_name="Ревьюер",
            model=rev_resp.model,
            output=rev_resp.content,
            cost_usd=rev_resp.cost_usd,
            latency_ms=rev_resp.latency_ms,
        ))

        elapsed = int((time.monotonic() - start) * 1000)
        self._memory.save_task(
            task_type=str(TaskType.REFACTOR),
            prompt=f"refactor {path_str}",
            model_used=f"{arch_model} → {dev_model} → {rev_model}",
            result_summary=rev_resp.content[:500],
            cost_usd=total_cost,
            project_path=str(self.root),
            status="completed",
        )

        return OrchestratorResult(
            task_type=TaskType.REFACTOR,
            success=True,
            primary_output=rev_resp.content,
            pipeline_steps=pipeline_steps,
            total_cost_usd=total_cost,
            total_latency_ms=elapsed,
            model_used=rev_resp.model,
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
