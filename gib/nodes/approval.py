"""Node: Human Approval — показывает diff и запрашивает подтверждение."""
from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from gib.core.state import GibState
from gib.core.types import ApprovalStatus, PatchFile
from gib.utils import get_logger
from gib.utils.console import console
from gib.utils.theme import BORDER, BORDER_BRIGHT, ERROR, GREEN, TEXT_DIM, WARNING

logger = get_logger("gib.nodes.approval")


def _render_diff(diff: str, max_lines: int = 60) -> None:
    if not diff:
        return
    lines = diff.splitlines()
    if len(lines) > max_lines:
        diff = "\n".join(lines[:max_lines]) + f"\n... [ещё {len(lines) - max_lines} строк]"
    console.print(Syntax(diff, "diff", theme="monokai", line_numbers=False, background_color="#0D1117"))


def _render_approval_panel(state: GibState) -> None:
    patch_files: list[PatchFile] = state.get("patch_files", [])
    summary = state.get("approval_summary", "")
    cost = state.get("total_cost_usd", 0.0)
    latency = state.get("total_latency_ms", 0)
    models = state.get("models_used", [])
    security_issues = state.get("security_issues", [])
    review = state.get("review_result", "")[:500]
    warnings = state.get("warnings", [])

    console.rule(f"[bold {GREEN}]проверка изменений[/]", style=BORDER_BRIGHT)

    for w in warnings:
        console.print(f"[warning]⚠[/] {w}")

    metrics = Table(show_header=False, box=None, padding=(0, 2))
    metrics.add_column(style=f"dim {TEXT_DIM}")
    metrics.add_column(style="bold")
    metrics.add_row("модели", " → ".join(models[-5:]) if models else "—")
    metrics.add_row("стоимость", f"[dim]{GREEN}${cost:.5f}[/]")
    metrics.add_row("время", f"{latency / 1000:.1f}с")
    metrics.add_row("файлы", str(len(patch_files)))
    if security_issues:
        critical = sum(1 for i in security_issues if i.severity == "critical")
        metrics.add_row(
            "безопасность",
            f"[error]{len(security_issues)} проблем (критических: {critical})[/]"
            if critical
            else f"[warning]{len(security_issues)} проблем[/]",
        )
    console.print(metrics)
    console.print()

    if patch_files:
        console.print(Panel(
            summary,
            title=f"[bold {GREEN}]●[/] [bold] Файлы[/]",
            border_style=BORDER,
        ))
        console.print()

        for pf in patch_files[:3]:
            console.print(f"[bold {GREEN}]▸[/] [bold]{pf.path}[/]")
            _render_diff(pf.diff, max_lines=30)
            console.print()

        if len(patch_files) > 3:
            console.print(f"[dim {TEXT_DIM}]... и ещё {len(patch_files) - 3} файлов[/]\n")

    if review:
        console.print(Panel(
            review,
            title=f"[bold {GREEN}]●[/] [bold] Ревью[/]",
            border_style=BORDER_BRIGHT,
        ))


async def node_approval(state: GibState) -> dict:
    """LangGraph Node: Human-in-the-loop одобрение изменений."""
    _render_approval_panel(state)

    critical_issues = [
        i for i in state.get("security_issues", [])
        if i.severity == "critical"
    ]

    if critical_issues:
        console.print(f"\n[error]⛔ ЗАБЛОКИРОВАНО: {len(critical_issues)} критических проблем[/]")
        for issue in critical_issues:
            console.print(f"  [error]• {issue.file}:{issue.line} — {issue.description}[/]")
        console.print(f"[warning]Исправьте критические проблемы перед применением.[/]\n")

        return {
            "approval_status": ApprovalStatus.REJECTED.value,
            "current_step": "approval_blocked",
            "logs": [f"[Approval] BLOCKED by {len(critical_issues)} critical security issues"],
        }

    auto_apply = bool(state.get("metadata", {}).get("auto_apply"))
    if auto_apply:
        console.print(f"\n[dim {TEXT_DIM}]Автоприменение — изменения будут записаны без подтверждения.[/]\n")
        approved = True
    else:
        try:
            approved = Confirm.ask(
                f"\n[bold]Применить эти изменения?[/bold]",
                default=False,
            )
        except (KeyboardInterrupt, EOFError):
            approved = False

    if approved:
        status = ApprovalStatus.APPROVED.value
        logger.info("[approval] Пользователь одобрил изменения")
        log_msg = "[Approval] User approved changes"
    else:
        status = ApprovalStatus.REJECTED.value
        logger.info("[approval] Пользователь отклонил изменения")
        log_msg = "[Approval] User rejected changes"

    return {
        "approval_status": status,
        "current_step": "approved" if approved else "rejected",
        "logs": [log_msg],
    }


def route_after_approval(state: GibState) -> str:
    status = state.get("approval_status", ApprovalStatus.PENDING.value)
    if status == ApprovalStatus.APPROVED.value:
        return "apply"
    return "skip"
