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

from gib.orchestrator import OrchestratorResult
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
    table.add_row("[dim]Language[/]", f"[cyan]{p.language}[/]")
    table.add_row("[dim]Framework[/]", f"[cyan]{p.framework}[/]")
    table.add_row("[dim]Package manager[/]", f"[cyan]{p.package_manager}[/]")
    table.add_row("[dim]Git[/]", "[green]yes[/]" if p.has_git else "[red]no[/]")
    table.add_row("[dim]Docker[/]", "[green]yes[/]" if p.has_docker else "[dim]no[/]")
    table.add_row("[dim]Tests[/]", "[green]yes[/]" if p.has_tests else "[yellow]no[/]")
    console.print(Panel(table, title="[dim]Project[/]", border_style="dim", expand=False))


def print_result(result: OrchestratorResult, show_meta: bool = True) -> None:
    """Print the orchestrator result with metadata."""
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


def confirm(prompt: str = "Apply changes?") -> bool:
    """Ask user for Y/N confirmation."""
    console.print(f"\n[bold]{prompt}[/]")
    console.print("  [bold green]\\[Y][/] Yes   [bold red]\\[N][/] No")
    while True:
        try:
            answer = input("  > ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Cancelled[/]")
            return False
        if answer in ("Y", "YES", ""):
            return True
        if answer in ("N", "NO"):
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
