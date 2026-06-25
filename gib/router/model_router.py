"""Intelligent Model Router — selects the best model for each task type."""
from __future__ import annotations

from enum import StrEnum

from gib.config import get_config
from gib.utils import get_logger

logger = get_logger("gib.router")


class TaskType(StrEnum):
    GENERAL = "general"
    ARCHITECTURE = "architecture"
    REFACTOR = "refactor"
    DOCS = "docs"
    TEST = "test"
    REVIEW = "review"
    FIX = "fix"
    COMMIT = "commit"
    EXPLAIN = "explain"
    DOCTOR = "doctor"
    WATCH = "watch"
    CHAT = "chat"


# Keywords to detect task type from free-form prompts
_TASK_KEYWORDS: dict[TaskType, list[str]] = {
    TaskType.FIX: ["fix", "bug", "error", "исправь", "ошибк", "починить", "сломан"],
    TaskType.REFACTOR: ["refactor", "рефактор", "улучши", "переписать", "optimize", "optimiz"],
    TaskType.TEST: ["test", "тест", "coverage", "покрыти", "spec", "unit", "integration"],
    TaskType.DOCS: ["docs", "document", "докумен", "readme", "комментар", "explain"],
    TaskType.REVIEW: ["review", "ревью", "проверь", "audit", "аудит"],
    TaskType.ARCHITECTURE: ["architect", "архитект", "design", "дизайн", "structure", "структур"],
    TaskType.COMMIT: ["commit", "коммит", "message", "changelog"],
}


class ModelRouter:
    """Routes tasks to the most appropriate model."""

    def __init__(self) -> None:
        self._config = get_config()

    def detect_task_type(self, prompt: str) -> TaskType:
        """Detect task type from a free-form prompt."""
        lower = prompt.lower()
        for task_type, keywords in _TASK_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                logger.debug("Detected task type: %s", task_type)
                return task_type
        return TaskType.GENERAL

    def select_model(self, task_type: TaskType | str) -> str:
        """Select the best model for the given task type."""
        model = self._config.model_for_task(str(task_type))
        logger.debug("Selected model %s for task %s", model, task_type)
        return model

    def route(self, prompt: str, task_type: TaskType | None = None) -> tuple[TaskType, str]:
        """
        Given a prompt (and optional explicit task type), return
        (detected_task_type, selected_model).
        """
        resolved_type = task_type or self.detect_task_type(prompt)
        model = self.select_model(resolved_type)
        return resolved_type, model
