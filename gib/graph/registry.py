"""Workflow Registry — центральный реестр всех workflow.

Добавление нового workflow:
1. Создайте файл в gib/workflows/
2. Унаследуйте от BaseWorkflow
3. Зарегистрируйте здесь одной строкой

Никаких изменений в остальном коде не требуется.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from gib.core.types import WorkflowType
from gib.workflows.base import BaseWorkflow

if TYPE_CHECKING:
    pass

# Реестр: workflow_type → класс workflow
_REGISTRY: dict[str, type[BaseWorkflow]] = {}


def register(workflow_type: WorkflowType):
    """Декоратор для регистрации workflow."""
    def decorator(cls: type[BaseWorkflow]) -> type[BaseWorkflow]:
        _REGISTRY[workflow_type.value] = cls
        return cls
    return decorator


def _load_all() -> None:
    """Ленивая загрузка всех workflow при первом обращении."""
    if _REGISTRY:
        return

    from gib.workflows.feature import FeatureWorkflow
    from gib.workflows.bugfix import BugFixWorkflow
    from gib.workflows.review import ReviewWorkflow
    from gib.workflows.refactor import RefactorWorkflow
    from gib.workflows.explain import ExplainWorkflow
    from gib.workflows.doctor import DoctorWorkflow

    _REGISTRY[WorkflowType.FEATURE.value] = FeatureWorkflow
    _REGISTRY[WorkflowType.BUGFIX.value] = BugFixWorkflow
    _REGISTRY[WorkflowType.REVIEW.value] = ReviewWorkflow
    _REGISTRY[WorkflowType.REFACTOR.value] = RefactorWorkflow
    _REGISTRY[WorkflowType.EXPLAIN.value] = ExplainWorkflow
    _REGISTRY[WorkflowType.DOCTOR.value] = DoctorWorkflow


class WorkflowRegistry:
    """Фабрика workflow."""

    @staticmethod
    def get(workflow_type: str | WorkflowType) -> type[BaseWorkflow]:
        """Возвращает класс workflow по типу."""
        _load_all()
        key = workflow_type.value if isinstance(workflow_type, WorkflowType) else workflow_type
        if key not in _REGISTRY:
            raise KeyError(f"Unknown workflow type: {key!r}. Available: {list(_REGISTRY.keys())}")
        return _REGISTRY[key]

    @staticmethod
    def list() -> list[str]:
        """Список зарегистрированных workflow."""
        _load_all()
        return list(_REGISTRY.keys())

    @staticmethod
    async def run(workflow_type: str | WorkflowType, initial_state: dict) -> dict:
        """Запускает workflow и возвращает финальное состояние."""
        _load_all()
        workflow_cls = WorkflowRegistry.get(workflow_type)
        return await workflow_cls.run(initial_state)


def get_workflow(workflow_type: str | WorkflowType) -> type[BaseWorkflow]:
    """Shorthand для WorkflowRegistry.get()."""
    return WorkflowRegistry.get(workflow_type)
