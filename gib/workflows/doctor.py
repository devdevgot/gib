"""Doctor Workflow — полная диагностика проекта.

Граф:
  analyzer → context_builder → [reviewer ‖ security ‖ researcher] → END
  Параллельный анализ со всех сторон.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from gib.core.state import GibState
from gib.nodes.analyzer import node_project_analyzer
from gib.nodes.context_builder import node_context_builder
from gib.nodes.reviewer import node_reviewer
from gib.nodes.security import node_security
from gib.nodes.researcher import node_researcher
from gib.workflows.base import BaseWorkflow


def _parallel_doctor(state: GibState):
    """Fan-out на все диагностические узлы одновременно."""
    return [
        Send("reviewer", state),
        Send("security", state),
        Send("researcher", state),
    ]


async def _node_doctor_merge(state: GibState) -> dict:
    """Собирает результаты диагностики в финальный отчёт."""
    review = state.get("review_result", "")
    research = state.get("research_result", "")
    security_issues = state.get("security_issues", [])

    # Собираем отчёт
    sections: list[str] = ["# 🩺 Отчёт GIB Doctor\n"]

    if review:
        sections.append(f"## Ревью качества кода\n{review[:2000]}")

    if security_issues:
        sec_lines = [f"## Сканирование безопасности — найдено проблем: {len(security_issues)}"]
        for issue in security_issues[:10]:
            sec_lines.append(
                f"- [{issue.severity.upper()}] {issue.file}:{issue.line} "
                f"— {issue.description}"
            )
        sections.append("\n".join(sec_lines))
    else:
        sections.append("## Сканирование безопасности\n✅ Проблем не обнаружено")

    if research:
        sections.append(f"## Рекомендации и best practices\n{research[:1500]}")

    final = "\n\n".join(sections)

    return {
        "final_output": final,
        "success": True,
        "current_step": "done",
        "logs": ["[Doctor] Диагностика завершена"],
    }


class DoctorWorkflow(BaseWorkflow):
    """
    Doctor Workflow: параллельная диагностика — code review + security + best practices.
    """

    @classmethod
    def build_graph(cls):
        g = StateGraph(GibState)

        g.add_node("analyzer", node_project_analyzer)
        g.add_node("context_builder", node_context_builder)
        g.add_node("reviewer", node_reviewer)
        g.add_node("security", node_security)
        g.add_node("researcher", node_researcher)
        g.add_node("doctor_merge", _node_doctor_merge)

        g.set_entry_point("analyzer")
        g.add_edge("analyzer", "context_builder")

        # Параллельный запуск диагностики
        g.add_conditional_edges("context_builder", _parallel_doctor, ["reviewer", "security", "researcher"])

        # Все три → merge
        g.add_edge("reviewer", "doctor_merge")
        g.add_edge("security", "doctor_merge")
        g.add_edge("researcher", "doctor_merge")

        g.add_edge("doctor_merge", END)

        return g
