"""Node: TaskPlanner — Claude разбивает задачу на независимые подзадачи.

Никаких параллельных запросов здесь — только планирование.
"""
from __future__ import annotations

import json
import re
from typing import Any

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentRole, SubTask, TaskType
from gib.utils import get_logger

logger = get_logger("gib.nodes.task_planner")

_PLANNER_SYSTEM = """\
You are a senior software architect. Your job is to analyze a user's request and decompose it into \
independent, parallelizable subtasks.

Each subtask should:
- Have a single clear responsibility
- Be independently executable
- Map to exactly one agent role

Available agent roles: architect, developer, researcher, reviewer, tester

Respond ONLY with valid JSON in this exact format:
{
  "plan_summary": "brief description of the overall approach",
  "subtasks": [
    {
      "id": "task_1",
      "title": "Short title",
      "description": "Detailed description of what needs to be done",
      "agent_role": "architect|developer|researcher|reviewer|tester",
      "depends_on": [],
      "priority": 1
    }
  ]
}
"""


def _build_planner_prompt(state: GibState) -> str:
    ctx = state.get("project_context", {})
    stack = state.get("detected_stack", {})
    deps = state.get("dependencies_raw", "")[:4000]
    readme = state.get("readme_content", "")[:2000]
    session_context = state.get("session_context", "")

    parts = [
        f"## User Request\n{state.get('user_request', '')}",
    ]
    if session_context:
        parts.append(f"\n## Project Memory\n{session_context[:8000]}")
    parts.extend([
        f"\n## Project Info\nLanguage: {ctx.get('language', 'Unknown')}",
        f"Frameworks: {', '.join(stack.get('frameworks', []))}",
        f"Has Docker: {ctx.get('has_docker', False)}",
    ])
    if deps:
        parts.append(f"\n## Dependencies (truncated)\n{deps}")
    if readme:
        parts.append(f"\n## README (truncated)\n{readme}")

    return "\n".join(parts)


def _parse_subtasks(raw: str) -> tuple[str, list[SubTask]]:
    """Парсит ответ Claude в список SubTask."""
    # Ищем JSON блок
    match = re.search(r"\{[\s\S]+\}", raw)
    if not match:
        return "Could not parse plan", []

    try:
        data = json.loads(match.group())
        plan_summary = data.get("plan_summary", "")
        subtasks: list[SubTask] = []
        for item in data.get("subtasks", []):
            try:
                role_str = item.get("agent_role", "developer")
                role = AgentRole(role_str)
            except ValueError:
                role = AgentRole.DEVELOPER
            subtasks.append(SubTask(
                id=item.get("id", f"task_{len(subtasks)+1}"),
                title=item.get("title", ""),
                description=item.get("description", ""),
                agent_role=role,
                depends_on=item.get("depends_on", []),
                priority=item.get("priority", 1),
            ))
        return plan_summary, subtasks
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("[task_planner] JSON parse error: %s", e)
        return raw[:500], []


async def node_task_planner(state: GibState) -> dict:
    """
    LangGraph Node: Claude разбивает задачу на подзадачи.
    """
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = router.select_model(TaskType.ARCHITECTURE)
    prompt = _build_planner_prompt(state)

    logger.info("[task_planner] Планирую задачу с %s", model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_PLANNER_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.2,
        max_tokens=4096,
    )

    plan_summary, subtasks = _parse_subtasks(resp.content)

    # Выбираем модели для каждой роли
    selected_models = {
        AgentRole.ARCHITECT.value: router.select_model(TaskType.ARCHITECTURE),
        AgentRole.DEVELOPER.value: router.select_model(TaskType.DEVELOPMENT),
        AgentRole.RESEARCHER.value: router.select_model(TaskType.RESEARCH),
        AgentRole.REVIEWER.value: router.select_model(TaskType.REVIEW),
        AgentRole.TESTER.value: router.select_model(TaskType.TESTING),
    }

    logger.info("[task_planner] Создал %d подзадач", len(subtasks))

    return {
        "execution_plan": plan_summary,
        "subtasks": subtasks,
        "selected_models": selected_models,
        "current_step": "planned",
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[TaskPlanner] Plan: {plan_summary[:200]}"],
    }
