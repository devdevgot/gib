"""Rich UI helpers for GIB CLI output."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from gib.orchestrator import OrchestratorResult, PipelineStep
from gib.utils.console import console


def print_banner() -> None:
    """Print GIB banner."""
    console.print(
        Panel.fit(
            "[bold cyan]GIB[/] [dim]— AI Development Operating System[/]",
            border_style="cyan",
        )
    )


def print_project_info(result: OrchestratorResult) -> None:
    """Print project analysis summary."""
    if not result.project_profile:
        return
    p = result.project_profile
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("[dim]Язык[/]", f"[cyan]{p.language}[/]")
    table.add_row("[dim]Фреймворк[/]", f"[cyan]{p.framework}[/]")
    table.add_row("[dim]Менеджер пакетов[/]", f"[cyan]{p.package_manager}[/]")
    table.add_row("[dim]Git[/]", "[green]есть[/]" if p.has_git else "[red]нет[/]")
    table.add_row("[dim]Docker[/]", "[green]есть[/]" if p.has_docker else "[dim]нет[/]")
    table.add_row("[dim]Тесты[/]", "[green]есть[/]" if p.has_tests else "[yellow]нет[/]")
    console.print(Panel(table, title="[dim]Проект[/]", border_style="dim", expand=False))


def print_pipeline_steps(steps: list[PipelineStep]) -> None:
    """Показывает шаги пайплайна в виде цепочки агентов."""
    if not steps:
        return

    # Заголовок пайплайна
    console.print()
    console.print(Rule("[dim]Пайплайн агентов[/]", style="dim"))

    # Краткая цепочка: Архитектор → Разработчик → Ревьюер
    chain_parts = []
    for step in steps:
        model_short = step.model.split("/")[-1] if "/" in step.model else step.model
        chain_parts.append(f"[cyan]{step.agent_name}[/] [dim]({model_short})[/]")
    console.print("  " + " [dim]→[/] ".join(chain_parts))
    console.print()

    # Детали каждого шага
    for step in steps:
        cost_str = f"${step.cost_usd:.4f}" if step.cost_usd >= 0.001 else f"${step.cost_usd * 1000:.4f}m"
        model_short = step.model.split("/")[-1] if "/" in step.model else step.model
        console.print(
            f"  [bold cyan]Шаг {step.step}[/] [dim]·[/] [yellow]{step.agent_name}[/] "
            f"[dim]·[/] {model_short} [dim]·[/] {cost_str} [dim]·[/] {step.latency_ms}ms"
        )


def print_result(result: OrchestratorResult, show_meta: bool = True) -> None:
    """Print the orchestrator result with metadata."""
    # Если это пайплайн — показываем шаги перед результатом
    if result.is_pipeline and result.pipeline_steps:
        print_pipeline_steps(result.pipeline_steps)
        console.print(Rule("[dim]Финальный результат (ревью)[/]", style="dim"))
        console.print()

    # Main output
    output = result.primary_output.strip()
    if output:
        console.print(Markdown(output))

    if show_meta:
        console.print()
        _print_meta_line(result)


def _print_meta_line(result: OrchestratorResult) -> None:
    """Print cost / time / model as a single dim line."""
    parts: list[str] = []
    if result.is_pipeline:
        parts.append(f"[dim]pipeline[/]")
    if result.model_used:
        parts.append(f"[model]{result.model_used}[/]")
    if result.total_cost_usd > 0:
        parts.append(f"[cost]{result.cost_str()}[/]")
    if result.total_latency_ms > 0:
        parts.append(f"[dim]{result.total_latency_ms}ms[/]")
    if parts:
        console.print("  " + "  ·  ".join(parts))


def print_diff(diff: str) -> None:
    """Print a git diff with syntax highlighting."""
    if diff:
        console.print(Syntax(diff, "diff", theme="monokai", line_numbers=False))
    else:
        console.print("[dim]No changes[/]")


def confirm(prompt: str = "Применить изменения?") -> bool:
    """Ask user for Y/N confirmation."""
    console.print(f"\n[bold]{prompt}[/]")
    console.print("  [bold green]\\[Y][/] Да   [bold red]\\[N][/] Нет")
    while True:
        try:
            answer = input("  > ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Отмена[/]")
            return False
        if answer in ("Y", "YES", "Д", "ДА", ""):
            return True
        if answer in ("N", "NO", "Н", "НЕТ"):
            return False


@contextmanager
def spinner(message: str) -> Generator[None, None, None]:
    """Show a spinner while work is in progress."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(message, total=None)
        yield


def print_error(message: str) -> None:
    console.print(f"[error]✗ {message}[/]")


def print_success(message: str) -> None:
    console.print(f"[success]✓ {message}[/]")


def print_warning(message: str) -> None:
    console.print(f"[warning]⚠ {message}[/]")
