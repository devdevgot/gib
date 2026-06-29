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
    help="GIB — AI-операционная система для разработки",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=False,
)

# Known subcommands — used by the entrypoint wrapper to route correctly
_SUBCOMMANDS = {
    "review", "fix", "refactor", "commit", "doctor",
    "explain", "test", "docs", "watch", "chat", "resume", "free",
}


def _run(coro):
    from gib.providers.errors import CreditsExhaustedError
    from gib.cli import ui

    try:
        return asyncio.run(coro)
    except CreditsExhaustedError as e:
        ui.print_credits_paused(str(e))
        raise typer.Exit(2) from e


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
        "[bold cyan]GIB[/] — AI-ассистент для разработки\n\n"
        "[dim]Свободная задача (без кавычек):[/]\n"
        "  [cyan]gib улучши страницу дашборда[/]\n"
        "  [cyan]gib добавь валидацию в форму регистрации[/]\n"
        "  [cyan]gib -y исправь медленную загрузку списка[/]  [dim](без подтверждения)[/]\n\n"
        "[dim]Команды:[/]\n"
        "  [cyan]gib review[/]            [dim]Код-ревью[/]\n"
        "  [cyan]gib fix [файл][/]        [dim]Исправить баги[/]\n"
        "  [cyan]gib refactor [путь][/]   [dim]Рефакторинг кода[/]\n"
        "  [cyan]gib test [файл][/]       [dim]Сгенерировать тесты[/]\n"
        "  [cyan]gib docs [файл][/]       [dim]Сгенерировать документацию[/]\n"
        "  [cyan]gib commit[/]            [dim]Умный git-коммит[/]\n"
        "  [cyan]gib doctor[/]            [dim]Глубокая диагностика[/]\n"
        "  [cyan]gib explain <путь>[/]    [dim]Объяснить код[/]\n"
        "  [cyan]gib watch [папка][/]     [dim]Слежение за файлами[/]\n"
        "  [cyan]gib chat[/]              [dim]Интерактивный чат[/]\n"
        "  [cyan]gib resume[/]           [dim]Продолжить после нехватки кредитов[/]\n"
        "  [cyan]gib set-key[/]           [dim]Изменить API ключ[/]",
        border_style="cyan",
        title="[bold]gib[/]",
    ))


# ─────────────────────────────────────────────────────────────
# Callback — handles: gib (no args) and gib "free prompt"
# ─────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", "-v", help="Показать версию")] = False,
) -> None:
    """GIB — AI-операционная система для разработки."""
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
    prompt_parts: Annotated[
        list[str],
        typer.Argument(help="Свободная задача — можно без кавычек"),
    ],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Применить изменения без подтверждения"),
    ] = False,
) -> None:
    """Выполнить задачу разработки по свободному запросу (внутренняя команда)."""
    from gib.utils.request import join_prompt_args, enrich_user_request

    prompt = enrich_user_request(join_prompt_args(prompt_parts))
    if not prompt:
        console.print("[red]Укажите задачу, например: gib улучши страницу дашборда[/]")
        raise typer.Exit(1)

    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]Claude[/] анализирует → [cyan]GLM 5.2[/] пишет → [cyan]Gemini[/] ревьюит..."):
            result = await orch.run_general(prompt, auto_apply=yes)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib review
# ─────────────────────────────────────────────────────────────

@app.command("review")
def cmd_review(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Файлы или папки для ревью")] = None,
) -> None:
    """Провести тщательное код-ревью."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]Проверяю код...[/]"):
            result = await orch.run_review(resolved)
        ui.print_project_info(result)
        ui.print_result(result)

        # Предлагаем исправить найденные проблемы
        if result.success and result.primary_output.strip():
            console.print()
            if ui.confirm("Исправить все найденные проблемы?"):
                console.print()
                with ui.spinner("[cyan]Исправляю проблемы...[/]"):
                    fix_result = await orch.run_fix(
                        paths=resolved,
                        review_context=result.primary_output,
                    )
                ui.print_result(fix_result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib fix
# ─────────────────────────────────────────────────────────────

@app.command("fix")
def cmd_fix(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Файлы для исправления")] = None,
    error: Annotated[str, typer.Option("--error", "-e", help="Текст ошибки")] = "",
) -> None:
    """Исправить баги в кодовой базе."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]GLM 5.2[/] исправляет → [cyan]Gemini[/] проверяет..."):
            result = await orch.run_fix(resolved, error=error)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib refactor
# ─────────────────────────────────────────────────────────────

@app.command("refactor")
def cmd_refactor(
    paths: Annotated[list[Path], typer.Argument(help="Файлы или папки для рефакторинга")],
) -> None:
    """Рефакторинг кода по принципам SOLID и чистого кода."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]Claude[/] планирует → [cyan]GLM 5.2[/] рефакторит → [cyan]Gemini[/] проверяет..."):
            result = await orch.run_refactor([Path(p) for p in paths])
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib commit
# ─────────────────────────────────────────────────────────────

@app.command("commit")
def cmd_commit(
    auto: Annotated[bool, typer.Option("--auto", "-a", help="Коммит без подтверждения")] = False,
) -> None:
    """Сгенерировать сообщение коммита и при необходимости закоммитить."""
    _ensure_api_key()
    from gib.cli import ui
    from gib.git import GitIntegration

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]Генерирую сообщение коммита...[/]"):
            result = await orch.run_commit()

        if not result.success:
            ui.print_error(result.primary_output)
            raise typer.Exit(1)

        console.print()
        console.print(Panel(
            f"[bold]{result.primary_output}[/]",
            title="[dim]Предлагаемое сообщение коммита[/]",
            border_style="cyan",
        ))

        git = GitIntegration(Path.cwd())
        status = git.status()
        if status:
            console.print(f"\n[dim]Изменения:[/]\n{status}")

        if auto or ui.confirm("Закоммитить с этим сообщением?"):
            git.commit(result.primary_output)
            ui.print_success("Закоммичено!")
        else:
            console.print("[dim]Коммит отменён.[/]")

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib doctor
# ─────────────────────────────────────────────────────────────

@app.command("doctor")
def cmd_doctor() -> None:
    """Глубокая диагностика: баги, мёртвый код, безопасность, архитектура."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner("[cyan]Запускаю диагностику...[/]"):
            result = await orch.run_doctor()
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib explain
# ─────────────────────────────────────────────────────────────

@app.command("explain")
def cmd_explain(
    path: Annotated[Path, typer.Argument(help="Файл или папка для объяснения")],
) -> None:
    """Подробно объяснить файл или директорию."""
    _ensure_api_key()
    from gib.cli import ui

    if not path.exists():
        ui.print_error(f"Путь не найден: {path}")
        raise typer.Exit(3)

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner(f"[cyan]Объясняю {path}...[/]"):
            result = await orch.run_explain(path)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib test
# ─────────────────────────────────────────────────────────────

@app.command("test")
def cmd_test(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Файлы для генерации тестов")] = None,
) -> None:
    """Сгенерировать тесты для вашего кода."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]Генерирую тесты...[/]"):
            result = await orch.run_test(resolved)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib docs
# ─────────────────────────────────────────────────────────────

@app.command("docs")
def cmd_docs(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Файлы для документирования")] = None,
) -> None:
    """Сгенерировать документацию для вашего кода."""
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        resolved = [Path(p) for p in paths] if paths else None
        with ui.spinner("[cyan]Генерирую документацию...[/]"):
            result = await orch.run_docs(resolved)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib watch
# ─────────────────────────────────────────────────────────────

@app.command("watch")
def cmd_watch(
    path: Annotated[Optional[Path], typer.Argument(help="Папка для слежения")] = None,
) -> None:
    """Следить за изменениями файлов и давать AI-обратную связь в реальном времени."""
    _ensure_api_key()
    from gib.cli.watch import start_watch

    watch_path = path or Path.cwd()
    console.print(f"[cyan]Слежу за[/] {watch_path}  [dim](Ctrl+C для остановки)[/]")
    _run(start_watch(watch_path))


# ─────────────────────────────────────────────────────────────
# gib chat
# ─────────────────────────────────────────────────────────────

@app.command("chat")
def cmd_chat() -> None:
    """Открыть интерактивный чат с контекстом проекта."""
    _ensure_api_key()
    from gib.cli.chat import start_chat
    _run(start_chat())


# ─────────────────────────────────────────────────────────────
# gib resume
# ─────────────────────────────────────────────────────────────

@app.command("resume")
def cmd_resume(
    thread_id: Annotated[
        Optional[str],
        typer.Option("--id", help="ID потока приостановленной задачи для возобновления"),
    ] = None,
    list_runs: Annotated[
        bool,
        typer.Option("--list", "-l", help="Список приостановленных задач"),
    ] = False,
) -> None:
    """Возобновить задачу, приостановленную из-за нехватки кредитов OpenRouter."""
    _ensure_api_key()
    from gib.cli import ui

    orch = _get_orchestrator()

    if list_runs:
        runs = orch.list_paused_runs()
        if not runs:
            console.print("[dim]Нет приостановленных задач для этого проекта.[/]")
            raise typer.Exit()
        console.print("[bold]Приостановленные задачи:[/]\n")
        for run in runs:
            ts = run.updated_at.strftime("%Y-%m-%d %H:%M") if run.updated_at else "?"
            console.print(
                f"  [cyan]{run.thread_id[:8]}…[/]  [dim]{ts}[/]  "
                f"[bold]{run.workflow_type}[/]  {run.user_request[:60]}"
            )
        console.print("\n[dim]Продолжить:[/] [cyan]gib resume --id <thread_id>[/]")
        raise typer.Exit()

    async def _run_it():
        with ui.spinner("[cyan]Возобновляю задачу с последнего checkpoint..."):
            result = await orch.run_resume(thread_id)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


# ─────────────────────────────────────────────────────────────
# gib free — бесплатный режим (free tier models)
# ─────────────────────────────────────────────────────────────

@app.command("free")
def cmd_free(
    prompt: Annotated[str, typer.Argument(help="Задача для выполнения")],
) -> None:
    """Выполнить задачу на бесплатных моделях (без затрат).

    Pipeline: Nemotron Ultra → North Mini Code → Laguna M.1 → North Mini Code → Laguna M.1
    """
    _ensure_api_key()
    from gib.cli import ui

    async def _run_it():
        orch = _get_orchestrator()
        with ui.spinner(
            "[cyan]Nemotron[/] планирует → [cyan]NorthMini[/] пишет → [cyan]Laguna[/] ревьюит... [dim](free)[/]"
        ):
            result = await orch.run_free(prompt)
        ui.print_project_info(result)
        ui.print_result(result)

    _run(_run_it())


@app.command("set-key")
def cmd_set_key() -> None:
    """Обновить API-ключ OpenRouter."""
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
