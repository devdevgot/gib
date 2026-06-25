"""GIB Core Types — enums, dataclasses, protocols."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class TaskType(str, Enum):
    """Тип задачи, управляет выбором модели."""
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"
    RESEARCH = "research"
    REVIEW = "review"
    SECURITY = "security"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    EXPLANATION = "explanation"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    GENERAL = "general"
    DOCTOR = "doctor"
    COMMIT = "commit"


class WorkflowType(str, Enum):
    """Тип workflow — определяет граф LangGraph."""
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REVIEW = "review"
    REFACTOR = "refactor"
    EXPLAIN = "explain"
    DOCTOR = "doctor"


class AgentRole(str, Enum):
    """Роль агента в пайплайне."""
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    SECURITY = "security"
    TESTER = "tester"
    SUPERVISOR = "supervisor"


class ApprovalStatus(str, Enum):
    """Статус одобрения от пользователя."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class ReviewVerdict(str, Enum):
    """Вердикт ревьюера."""
    APPROVED = "approved"
    NEEDS_FIX = "needs_fix"
    REJECTED = "rejected"


@dataclass
class ModelInfo:
    """Метаданные модели из OpenRouter."""
    model_id: str
    name: str
    context_window: int
    cost_per_1k_input: float   # USD
    cost_per_1k_output: float  # USD
    strengths: list[str] = field(default_factory=list)
    max_output_tokens: int = 8192


@dataclass
class SubTask:
    """Подзадача от TaskPlanner."""
    id: str
    title: str
    description: str
    agent_role: AgentRole
    depends_on: list[str] = field(default_factory=list)
    priority: int = 0


@dataclass
class PatchFile:
    """Один файл в патче."""
    path: str
    original: str
    modified: str
    diff: str
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class AgentOutput:
    """Результат одного агента."""
    role: AgentRole
    model_id: str
    content: str
    cost_usd: float = 0.0
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityIssue:
    """Одна проблема безопасности."""
    severity: str         # critical / high / medium / low
    category: str         # injection / xss / secrets / jwt / etc
    file: str
    line: int
    description: str
    recommendation: str


@runtime_checkable
class WorkflowProtocol(Protocol):
    """Интерфейс workflow."""
    async def run(self, state: dict[str, Any]) -> dict[str, Any]: ...
    def get_graph(self): ...
