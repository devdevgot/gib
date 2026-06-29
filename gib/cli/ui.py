"""Rich UI helpers for GIB CLI — Cursor / Claude Code style."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from gib.orchestrator import OrchestratorResult, PipelineStep
from gib.utils.console import console
from gib.utils.theme import (
    BANNER_ART,
    BANNER_TAGLINE,
    BORDER,
    BORDER_BRIGHT,
    ERROR,
    GREEN,
    GREEN_DIM,
    GREEN_MUTED,
    TEXT_DIM,
    prompt_prefix,
    status_spinner_columns,
)


def print_banner() -> None:
    """Брендовый баннер GIB."""
    console.print()
    console.print(BANNER_ART)
    console.print(f"  {BANNER_TAGLINE}")
    console.print()


def print_project_info(result: OrchestratorResult) -> None:
    """Краткая сводка по проекту."""
    if not result.project_profile:
        return
    p = result.project_profile

    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column(style=f"dim {TEXT_DIM}")
    table.add_column(style="bold")

    def _yes_no(val: bool, yes: str = "да", no: str = "нет") -> str:
        return f"[bold {GREEN}]{yes}[/]" if val else f"[dim]{no}[/]"

    table.add_row("язык", f"[bold {GREEN}]{p.language}[/]")
    table.add_row("фреймворк", f"[bold {GREEN}]{p.framework}[/]")
    table.add_row("пакеты", f"[bold {GREEN}]{p.package_manager}[/]")
    table.add_row("git", _yes_no(p.has_git))
    table.add_row("docker", _yes_no(p.has_docker))
    table.add_row("тесты", _yes_no(p.has_tests))

    console.print(Panel(
        table,
        title=f"[bold {GREEN}]●[/] [bold] Проект[/]",
        border_style=BORDER,
        padding=(0, 1),
        expand=False,
    ))
    console.print()


def print_pipeline_steps(steps: list[PipelineStep]) -> None:
    """Цепочка агентов в стиле agent trace."""
    if not steps:
        return

    console.print(Rule(f"[bold {GREEN}]агенты[/]", style=BORDER_BRIGHT, characters="─"))
    console.print()

    chain: list[str] = []
    for step in steps:
        model_short = step.model.split("/")[-1] if "/" in step.model else step.model
        chain.append(f"[bold {GREEN}]{step.agent_name}[/][dim {TEXT_DIM}]/{model_short}[/]")
    console.print(Text.from_markup("  " + f" [dim {TEXT_DIM}]→[/] ".join(chain)))
    console.print()

    for step in steps:
        cost = (
            f"${step.cost_usd:.4f}"
            if step.cost_usd >= 0.001
            else f"${step.cost_usd * 1000:.4f}m"
        )
        model_short = step.model.split("/")[-1] if "/" in step.model else step.model
        console.print(
            f"  [bold {GREEN}]▸[/] [bold]{step.agent_name}[/]"
            f"  [dim {TEXT_DIM}]·[/]  {model_short}"
            f"  [dim {TEXT_DIM}]·[/]  [dim {GREEN_MUTED}]{cost}[/]"
            f"  [dim {TEXT_DIM}]·[/]  {step.latency_ms}ms"
        )
    console.print()


def print_result(result: OrchestratorResult, show_meta: bool = True) -> None:
    """Финальный результат задачи."""
    if result.is_pipeline and result.pipeline_steps:
        print_pipeline_steps(result.pipeline_steps)
        console.print(Rule(f"[bold {GREEN}]результат[/]", style=BORDER_BRIGHT, characters="─"))
        console.print()

    output = result.primary_output.strip()
    if output:
        console.print(Markdown(output, code_theme="monokai"))

    if show_meta:
        console.print()
        _print_meta_line(result)


def _print_meta_line(result: OrchestratorResult) -> None:
    parts: list[str] = []
    if result.is_pipeline:
        parts.append(f"[dim {TEXT_DIM}]pipeline[/]")
    if result.model_used:
        short = result.model_used.split("/")[-1]
        parts.append(f"[dim {TEXT_DIM}]model[/] [bold {GREEN}]{short}[/]")
    if result.total_cost_usd > 0:
        parts.append(f"[dim {TEXT_DIM}]cost[/] [dim {GREEN_MUTED}]{result.cost_str()}[/]")
    if result.total_latency_ms > 0:
        parts.append(f"[dim {TEXT_DIM}]{result.total_latency_ms}ms[/]")
    if parts:
        console.print("  " + f"  [dim {TEXT_DIM}]·[/]  ".join(parts))


def print_diff(diff: str) -> None:
    if diff:
        console.print(Syntax(diff, "diff", theme="monokai", line_numbers=False, background_color="#0D1117"))
    else:
        console.print(f"[dim {TEXT_DIM}]нет изменений[/]")


def confirm(prompt: str = "Применить изменения?") -> bool:
    console.print()
    console.print(f"[bold]{prompt}[/]")
    console.print(f"  [bold {GREEN}][Y][/][dim {TEXT_DIM}] да   [/][bold {GREEN}][N][/][dim {TEXT_DIM}] нет[/]")
    while True:
        try:
            console.print(prompt_prefix(), end="")
            answer = input("").strip().upper()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n[dim {TEXT_DIM}]отмена[/]")
            return False
        if answer in ("Y", "YES", "Д", "ДА", ""):
            return True
        if answer in ("N", "NO", "Н", "НЕТ"):
            return False


@contextmanager
def spinner(message: str) -> Generator[None, None, None]:
    styled = f"[bold {GREEN}]●[/] [dim {TEXT_DIM}]{message}[/]"
    with Progress(
        *status_spinner_columns(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(styled, total=None)
        yield


def print_credits_paused(message: str) -> None:
    console.print()
    console.print(Panel(
        f"[dim {TEXT_DIM}]{message}[/]\n\n"
        f"[bold]Прогресс сохранён.[/] После пополнения кредитов:\n"
        f"  [bold {GREEN}]gib resume[/]           [dim {TEXT_DIM}]— продолжить задачу[/]\n"
        f"  [bold {GREEN}]gib resume --list[/]    [dim {TEXT_DIM}]— список задач[/]",
        title=f"[bold {GREEN}]![/] [bold] Кредиты закончились[/]",
        border_style=ERROR,
        padding=(1, 2),
    ))


def print_error(message: str) -> None:
    console.print(f"[error]✗[/] {message}")


def print_success(message: str) -> None:
    console.print(f"[success]✓[/] {message}")


def print_warning(message: str) -> None:
    console.print(f"[warning]⚠[/] {message}")


def print_status(message: str) -> None:
    """Строка статуса (git, операции)."""
    console.print(f"[bold {GREEN}]●[/] {message}")


def print_help() -> None:
    """Справка по командам."""
    body = (
        f"[dim {TEXT_DIM}]Свободная задача (без кавычек):[/]\n"
        f"  [bold {GREEN}]gib улучши страницу дашборда[/]\n"
        f"  [bold {GREEN}]gib -y исправь медленную загрузку[/]  [dim {TEXT_DIM}](без подтверждения)[/]\n\n"
        f"[dim {TEXT_DIM}]Git:[/]\n"
        f"  [bold {GREEN}]gib пушни[/]  [bold {GREEN}]gib сделай пулл[/]  [bold {GREEN}]gib мержни main[/]\n"
        f"  [bold {GREEN}]gib добавь в гит[/]  [bold {GREEN}]gib статус гита[/]\n\n"
        f"[dim {TEXT_DIM}]Команды:[/]\n"
        f"  [bold {GREEN}]gib review[/]       [dim {TEXT_DIM}]код-ревью[/]\n"
        f"  [bold {GREEN}]gib fix[/]          [dim {TEXT_DIM}]исправить баги[/]\n"
        f"  [bold {GREEN}]gib refactor[/]    [dim {TEXT_DIM}]рефакторинг[/]\n"
        f"  [bold {GREEN}]gib test[/]         [dim {TEXT_DIM}]тесты[/]\n"
        f"  [bold {GREEN}]gib docs[/]        [dim {TEXT_DIM}]документация[/]\n"
        f"  [bold {GREEN}]gib commit[/]      [dim {TEXT_DIM}]умный коммит[/]\n"
        f"  [bold {GREEN}]gib doctor[/]      [dim {TEXT_DIM}]диагностика[/]\n"
        f"  [bold {GREEN}]gib explain[/]     [dim {TEXT_DIM}]объяснить код[/]\n"
        f"  [bold {GREEN}]gib watch[/]       [dim {TEXT_DIM}]live-фидбэк[/]\n"
        f"  [bold {GREEN}]gib chat[/]        [dim {TEXT_DIM}]интерактивный чат[/]\n"
        f"  [bold {GREEN}]gibf[/]            [dim {TEXT_DIM}]бесплатный режим[/]\n"
        f"  [bold {GREEN}]gib resume[/]      [dim {TEXT_DIM}]продолжить задачу[/]\n"
        f"  [bold {GREEN}]gib set-key[/]     [dim {TEXT_DIM}]API ключ[/]"
    )
    console.print()
    console.print(BANNER_ART)
    console.print(Panel(body, title=f"[bold {GREEN}]●[/] [bold] gib[/]", border_style=BORDER, padding=(1, 2)))
    console.print()

