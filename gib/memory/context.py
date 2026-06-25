"""Helpers for building cross-session project memory context."""
from __future__ import annotations

from pathlib import Path

from gib.memory.store import MemoryStore, TaskRecord


def normalize_project_path(project_path: str) -> str:
    """Canonical absolute path for consistent DB lookups."""
    if not project_path:
        return ""
    return str(Path(project_path).expanduser().resolve())


def extract_task_summary(final_state: dict) -> str:
    """Pick the best available output from a finished workflow state."""
    return (
        final_state.get("final_output")
        or final_state.get("review_result")
        or final_state.get("code_result")
        or final_state.get("research_result")
        or final_state.get("tests")
        or final_state.get("documentation")
        or ""
    )


def build_project_memory_context(
    store: MemoryStore,
    project_path: str,
    *,
    task_limit: int = 20,
    include_chat: bool = True,
) -> str:
    """
    Build text context from prior tasks and chat sessions for injection into workflows.
    """
    norm = normalize_project_path(project_path)
    if not norm:
        return ""

    tasks = store.recent_tasks(limit=task_limit, project_path=norm)
    if not tasks and project_path and project_path != norm:
        tasks = store.recent_tasks(limit=task_limit, project_path=project_path)

    sections: list[str] = []

    if tasks:
        sections.append("## Память проекта (предыдущие задачи GIB)")
        for t in reversed(tasks):
            sections.append(_format_task_record(t))

    if include_chat:
        chat_summary = store.get_recent_chat_summary(norm, limit_messages=12)
        if chat_summary:
            sections.append(chat_summary)

    return "\n\n".join(s for s in sections if s.strip())


def _format_task_record(task: TaskRecord) -> str:
    ts = task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else "?"
    header = f"### [{ts}] {task.task_type.upper()}: {task.prompt[:300]}"
    summary = (task.result_summary or "").strip()
    if summary:
        return f"{header}\n{summary[:50_000]}"
    return f"{header}\n(статус: {task.status}, результат не сохранён)"
