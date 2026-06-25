"""Node: Human Approval — показывает diff и запрашивает подтверждение.

Использует Rich для красивого отображения.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich import print as rprint

from gib.core.state import GibState
from gib.core.types import ApprovalStatus, PatchFile
from gib.utils import get_logger

logger = get_logger("gib.nodes.approval")
console = Console()


def _render_diff(diff: str, max_lines: int = 60) -> None:
    """Отображает diff с подсветкой."""
    if not diff:
        return
    lines = diff.splitlines()
    if len(lines) > max_lines:
        diff = "\n".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} more lines]"
    syntax = Syntax(diff, "diff", theme="monokai", line_numbers=False)
    console.print(syntax)


def _render_approval_panel(state: GibState) -> None:
    """Отображает полную информацию для одобрения."""
    patch_files: list[PatchFile] = state.get("patch_files", [])
    summary = state.get("approval_summary", "")
    cost = state.get("total_cost_usd", 0.0)
    latency = state.get("total_latency_ms", 0)
    models = state.get("models_used", [])
    security_issues = state.get("security_issues", [])
    review = state.get("review_result", "")[:500]
    warnings = state.get("warnings", [])

    # Заголовок
    console.rule("[bold yellow]GIB — Review Changes[/bold yellow]")

    # Warnings
    for w in warnings:
        rprint(f"[red]{w}[/red]")

    # Метрики в таблице
    metrics = Table(show_header=False, box=None, padding=(0, 2))
    metrics.add_column("Key", style="dim")
    metrics.add_column("Value", style="bold")
    metrics.add_row("Models", " → ".join(models[-5:]) if models else "—")
    metrics.add_row("Cost", f"${cost:.5f}")
    metrics.add_row("Time", f"{latency / 1000:.1f}s")
    metrics.add_row("Files", str(len(patch_files)))
    if security_issues:
        critical = sum(1 for i in security_issues if i.severity == "critical")
        metrics.add_row(
            "Security",
            f"[red]{len(security_issues)} issues (critical: {critical})[/red]"
            if critical else
            f"[yellow]{len(security_issues)} issues[/yellow]"
        )
    console.print(metrics)
    console.print()

    # Список файлов
    if patch_files:
        console.print(Panel(summary, title="[bold]Files to Change[/bold]", border_style="blue"))
        console.print()

        # Diff первых 3 файлов
        for pf in patch_files[:3]:
            console.print(f"[bold cyan]── {pf.path}[/bold cyan]")
            _render_diff(pf.diff, max_lines=30)
            console.print()

        if len(patch_files) > 3:
            console.print(f"[dim]... and {len(patch_files) - 3} more files[/dim]\n")

    # Краткое ревью
    if review:
        console.print(Panel(
            review,
            title="[bold]Reviewer Summary[/bold]",
            border_style="green",
        ))


async def node_approval(state: GibState) -> dict:
    """
    LangGraph Node: Human-in-the-loop одобрение изменений.
    
    Показывает diff и ждёт Yes/No от пользователя.
    """
    _render_approval_panel(state)

    # Проверяем критические уязвимости
    critical_issues = [
        i for i in state.get("security_issues", [])
        if i.severity == "critical"
    ]

    if critical_issues:
        console.print(
            f"\n[red bold]⛔ BLOCKED: {len(critical_issues)} critical security issues![/red bold]"
        )
        for issue in critical_issues:
            console.print(f"  [red]• {issue.file}:{issue.line} — {issue.description}[/red]")
        console.print("[yellow]Fix critical issues before applying.[/yellow]\n")

        return {
            "approval_status": ApprovalStatus.REJECTED.value,
            "current_step": "approval_blocked",
            "logs": [f"[Approval] BLOCKED by {len(critical_issues)} critical security issues"],
        }

    # Запрашиваем подтверждение
    try:
        approved = Confirm.ask(
            "\n[bold]Apply these changes?[/bold]",
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
    """Conditional edge: применить или пропустить изменения."""
    status = state.get("approval_status", ApprovalStatus.PENDING.value)
    if status == ApprovalStatus.APPROVED.value:
        return "apply"
    return "skip"
