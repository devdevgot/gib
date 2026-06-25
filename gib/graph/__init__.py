"""GIB Graph Registry — фабрика workflow по типу задачи."""
from .registry import WorkflowRegistry, get_workflow

__all__ = ["WorkflowRegistry", "get_workflow"]
