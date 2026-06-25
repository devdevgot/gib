"""Intelligent Model Router — выбирает лучшую модель для каждого типа задачи.

Поддерживает два источника TaskType:
- gib.router.TaskType (legacy, для обратной совместимости)
- gib.core.types.TaskType (новые workflow)

Провайдер: только OpenRouter.
"""
from __future__ import annotations

from enum import StrEnum

from gib.config import get_config
from gib.utils import get_logger

logger = get_logger("gib.router")


class TaskType(StrEnum):
    """Legacy TaskType — сохранён для обратной совместимости с CLI."""
    GENERAL = "general"
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"      # новый
    RESEARCH = "research"            # новый
    REFACTOR = "refactor"
    DOCS = "docs"
    DOCUMENTATION = "documentation"  # новый alias
    TEST = "test"
    TESTING = "testing"              # новый alias
    REVIEW = "review"
    FIX = "fix"
    BUGFIX = "bugfix"                # новый alias
    COMMIT = "commit"
    EXPLAIN = "explain"
    EXPLANATION = "explanation"      # новый alias
    DOCTOR = "doctor"
    WATCH = "watch"
    CHAT = "chat"
    SECURITY = "security"            # новый


# Keywords to detect task type from free-form prompts
_TASK_KEYWORDS: dict[TaskType, list[str]] = {
    TaskType.FIX: ["fix", "bug", "error", "исправь", "ошибк", "починить", "сломан"],
    TaskType.REFACTOR: ["refactor", "рефактор", "улучши", "переписать", "optimize", "optimiz"],
    TaskType.TEST: ["test", "тест", "coverage", "покрыти", "spec", "unit", "integration"],
    TaskType.DOCS: ["docs", "document", "докумен", "readme", "комментар", "explain"],
    TaskType.REVIEW: ["review", "ревью", "проверь", "audit", "аудит"],
    TaskType.ARCHITECTURE: ["architect", "архитект", "design", "дизайн", "structure", "структур"],
    TaskType.COMMIT: ["commit", "коммит", "message", "changelog"],
    TaskType.SECURITY: ["security", "безопасност", "уязвимост", "vuln", "inject"],
}

# Маппинг core.types.TaskType → legacy TaskType (для select_model)
_CORE_TO_LEGACY: dict[str, str] = {
    "architecture": TaskType.ARCHITECTURE,
    "development": TaskType.DEVELOPMENT,
    "research": TaskType.REVIEW,         # Gemini — тот же что и review
    "review": TaskType.REVIEW,
    "security": TaskType.SECURITY,
    "testing": TaskType.TEST,
    "documentation": TaskType.DOCS,
    "explanation": TaskType.EXPLAIN,
    "bugfix": TaskType.FIX,
    "refactor": TaskType.REFACTOR,
    "general": TaskType.GENERAL,
    "doctor": TaskType.DOCTOR,
    "commit": TaskType.COMMIT,
}


class ModelRouter:
    """Routes tasks to the most appropriate model via OpenRouter."""

    def __init__(self) -> None:
        self._config = get_config()

    def detect_task_type(self, prompt: str) -> TaskType:
        """Определяет тип задачи по тексту промпта."""
        lower = prompt.lower()
        for task_type, keywords in _TASK_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                logger.debug("Detected task type: %s", task_type)
                return task_type
        return TaskType.GENERAL

    def select_model(self, task_type: "TaskType | str") -> str:
        """
        Выбирает лучшую модель для типа задачи.
        
        Принимает как legacy TaskType, так и core.types.TaskType (строки).
        """
        # Конвертируем core TaskType в legacy если нужно
        task_str = task_type.value if hasattr(task_type, "value") else str(task_type)
        legacy = _CORE_TO_LEGACY.get(task_str, task_str)
        model = self._config.model_for_task(legacy)
        logger.debug("Selected model %s for task %s", model, task_type)
        return model

    def route(self, prompt: str, task_type: "TaskType | None" = None) -> tuple[TaskType, str]:
        """
        По промпту (и опциональному явному типу) возвращает
        (detected_task_type, selected_model).
        """
        resolved_type = task_type or self.detect_task_type(prompt)
        model = self.select_model(resolved_type)
        return resolved_type, model
