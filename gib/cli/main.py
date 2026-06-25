"""GIB CLI — main entry point with all commands."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel

from gib.utils.console import console

app = typer.Typer(
    name="gib",
    help="GIB — AI Development Operating System",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=False,
)

# Known subcommands — used by the entrypoint wrapper to route correctly
_SUBCOMMANDS = {
    "review", "fix", "refactor", "commit", "doctor",
    "explain", "test", "docs", "watch", "chat",
}


def _run(coro):
    return asyncio.run(coro)


def _get_orchestrator():
    from gib.orchestrator import Orchestrator
    return Orchestrator(root=Path.cwd())


def _read_masked(prompt_text: str) -> str:
    """Read input showing * for each character typed."""
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.formatted_text import FormattedText
    return pt_prompt(FormattedText([("", prompt_text)]), is_password=True)


def _setup_api_key() -> str:
    """Interactively ask for the API key and save it to ~/.gib/.env."""
    from gib.utils.console import console

    gib_dir = Path.home() / ".gib"
    gib_dir.mkdir(parents=True, exist_ok=True)
    env_file = gib_dir / ".env"

    console.print()
    console.print("[bold cyan]GIB[/] — первый запуск, нужен API ключ OpenRouter")
    console.print("[dim]Получить ключ:[/] [cyan]https://openrouter.ai/keys[/]")
    console.print()

    while True:
        try:
            key = _read_masked("  OpenRouter API key (sk-or-...): ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Отмена.[/]")
            raise typer.Exit(0)

        if key.startswith("sk-or-") and len(key) > 20:
            break
        console.print("[red]  ✗ Неверный формат. Ключ должен начинаться с sk-or-[/]")

    # Сохраняем
    with open(env_file, "a") as f:
        f.write(f"\nOPENROUTER_API_KEY={key}\n")

    import os
    os.environ["OPENROUTER_API_KEY"] = key

    console.print(f"[green]  ✓ Ключ сохранён в {env_file}[/]")
    console.print()
    return key


def _ensure_api_key() -> None:
    """Load ~/.gib/.env then check key; if missing — run interactive setup."""
    import os
    from dotenv import load_dotenv

    # Загружаем глобальный ~/.gib/.env
    global_env = Path.home() / ".gib" / ".env"
    if global_env.exists():
        load_dotenv(global_env, override=False)

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        _setup_api_key()
        return

    # Ключ есть — убедимся что get_config() его видит (кэш мог создаться раньше)
    os.environ["OPENROUTER_API_KEY"] = key


def _print_help() -> None:
    console.print(Panel.fit(
        "[bold cyan]GIB[/] — AI Development Operating System\n\n"
        "[dim]Free-form task:[/]\n"
        "  [cyan]gib \"Add JWT authentication\"[/]\n"
        "  [cyan]gib \"Исправь ошибку в auth.py\"[/]\n\n"
        "[dim]Commands:[/]\n"
        "  [cyan]gib review[/]            [dim]Code review[/]\n"
        "  [cyan]gib fix [file][/]        [dim]Fix bugs[/]\n"
        "  [cyan]gib refactor [path][/]   [dim]Refactor code[/]\n"
        "  [cyan]gib test [file][/]       [dim]Generate tests[/]\n"
        "  [cyan]gib docs [file][/]       [dim]Generate docs[/]\n"
        "  [cyan]gib commit[/]            [dim]Smart git commit[/]\n"
        "  [cyan]gib doctor[/]            [dim]Deep diagnostics[/]\n"
        "  [cyan]gib explain <path>[/]    [dim]Explain code[/]\n"
        "  [cyan]gib watch [dir][/]       [dim]Live file watcher[/]\n"
        "  [cyan]gib chat[/]              [dim]Interactive chat[/]",
        border_style="cyan",
        title="[bold]gib[/]",
    ))


# ─────────────────────────────────────────────────────────────
# Callback — handles: gib (no args) and gib "free prompt"
# ─────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", "-v", help="Show version")] = False,
) -> None:
    """GIB — AI Development Operating System."""
    if version:
        from gib import __version__
        console.print(f"gib {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is not None:
        return

    # If we got here with args, the entrypoint wrapper handled free-form prompts.
    # Just show help.
    _print_help()


# ─────────────────────────────────────────────────────────────
# gib ask "free prompt"
# ─────────────────────────────────────────────────────────────

@app.command("ask", hidden=True)
def cmd_ask(
    prompt: Annotated[str, typer.Argument(help="Free-form task prompt")],
) -> None:
    """Run any development task with a free-form prompt (internal command)."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]GIB[/] thinking..."):
            result = await orch.run_general(prompt)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib review
# ─────────────────────────────────────────────────────────────

@app.command("review")
def cmd_review(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Files or dirs to review")] = None,
) -> None:
    """Perform a thorough code review."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]Reviewing code...[/]"):
            result = await orch.run_review(resolved)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib fix
# ─────────────────────────────────────────────────────────────

@app.command("fix")
def cmd_fix(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Files to fix")] = None,
    error: Annotated[str, typer.Option("--error", "-e", help="Error message")] = "",
) -> None:
    """Fix bugs in the codebase."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]Fixing bugs...[/]"):
            result = await orch.run_fix(resolved, error=error)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib refactor
# ─────────────────────────────────────────────────────────────

@app.command("refactor")
def cmd_refactor(
    paths: Annotated[list[Path], typer.Argument(help="Files or directories to refactor")],
) -> None:
    """Refactor code following SOLID and clean code principles."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]Refactoring...[/]"):
            result = await orch.run_refactor([Path(p) for p in paths])
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib commit
# ─────────────────────────────────────────────────────────────

@app.command("commit")
def cmd_commit(
    auto: Annotated[bool, typer.Option("--auto", "-a", help="Commit without confirmation")] = False,
) -> None:
    """Generate a commit message and optionally commit."""
    _ensure_api_key()
    from gib.cli import ui
    from gib.git import GitIntegration

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]Generating commit message...[/]"):
            result = await orch.run_commit()

        if not result.success:
            ui.print_error(result.primary_output)
            raise typer.Exit(1)

        console.print()
        console.print(Panel(
            f"[bold]{result.primary_output}[/]",
            title="[dim]Suggested commit message[/]",
            border_style="cyan",
        ))

        git = GitIntegration(Path.cwd())
        status = git.status()
        if status:
            console.print(f"\n[dim]Changes:[/]\n{status}")

        if auto or ui.confirm("Commit with this message?"):
            git.commit(result.primary_output)
            ui.print_success("Committed!")
        else:
            console.print("[dim]Not committed.[/]")

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib doctor
# ─────────────────────────────────────────────────────────────

@app.command("doctor")
def cmd_doctor() -> None:
    """Deep diagnostic: bugs, dead code, security, architecture issues."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]Running diagnostics...[/]"):
            result = await orch.run_doctor()
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib explain
# ─────────────────────────────────────────────────────────────

@app.command("explain")
def cmd_explain(
    path: Annotated[Path, typer.Argument(help="File or directory to explain")],
) -> None:
    """Explain a file or directory in detail."""
    _ensure_api_key()
    from gib.cli import ui

    if not path.exists():
        ui.print_error(f"Path not found: {path}")
        raise typer.Exit(3)

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner(f"[cyan]Explaining {path}...[/]"):
            result = await orch.run_explain(path)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib test
# ─────────────────────────────────────────────────────────────

@app.command("test")
def cmd_test(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Files to generate tests for")] = None,
) -> None:
    """Generate comprehensive tests for your code."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]Generating tests...[/]"):
            result = await orch.run_test(resolved)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib docs
# ─────────────────────────────────────────────────────────────

@app.command("docs")
def cmd_docs(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Files to document")] = None,
) -> None:
    """Generate documentation for your code."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]Generating documentation...[/]"):
            result = await orch.run_docs(resolved)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib watch
# ─────────────────────────────────────────────────────────────

@app.command("watch")
def cmd_watch(
    path: Annotated[Optional[Path], typer.Argument(help="Directory to watch")] = None,
) -> None:
    """Watch for file changes and provide live AI feedback."""
    _ensure_api_key()
    from gib.cli.watch import start_watch

    watch_path = path or Path.cwd()
    console.print(f"[cyan]Watching[/] {watch_path}  [dim](Ctrl+C to stop)[/]")
    _run(start_watch(watch_path))


# ─────────────────────────────────────────────────────────────
# gib chat
# ─────────────────────────────────────────────────────────────

@app.command("chat")
def cmd_chat() -> None:
    """Open interactive chat mode with project context."""
    _ensure_api_key()
    from gib.cli.chat import start_chat
    _run(start_chat())


@app.command("set-key")
def cmd_set_key() -> None:
    """Update your OpenRouter API key."""
    import os

    gib_dir = Path.home() / ".gib"
    gib_dir.mkdir(parents=True, exist_ok=True)
    env_file = gib_dir / ".env"

    current = os.environ.get("OPENROUTER_API_KEY", "")
    if current:
        masked = current[:8] + "..." + current[-4:]
        console.print(f"[dim]Текущий ключ:[/] [cyan]{masked}[/]")

    console.print("[dim]Получить ключ:[/] [cyan]https://openrouter.ai/keys[/]")
    console.print()

    while True:
        try:
            key = _read_masked("  Новый OpenRouter API key (sk-or-...): ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Отмена.[/]")
            raise typer.Exit(0)

        if key.startswith("sk-or-") and len(key) > 20:
            break
        console.print("[red]  ✗ Неверный формат. Ключ должен начинаться с sk-or-[/]")

    # Читаем существующий .env, заменяем или добавляем ключ
    lines = []
    replaced = False
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                lines.append(f"OPENROUTER_API_KEY={key}")
                replaced = True
            else:
                lines.append(line)

    if not replaced:
        lines.append(f"OPENROUTER_API_KEY={key}")

    env_file.write_text("\n".join(lines) + "\n")
    os.environ["OPENROUTER_API_KEY"] = key

    console.print(f"[green]  ✓ Ключ обновлён в {env_file}[/]")


if __name__ == "__main__":
    app()
