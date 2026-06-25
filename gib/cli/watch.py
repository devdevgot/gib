"""Watch mode — monitors file changes and provides live AI feedback."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from gib.utils.console import console


_IGNORE_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build",
    ".venv", "venv", "env", ".env", "coverage", ".mypy_cache",
    ".pytest_cache", "logs",
}

_WATCH_EXTENSIONS = {
    ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs",
    ".java", ".cs", ".rb", ".php", ".vue", ".svelte",
}


class _ChangeHandler:
    """Handles file system events."""

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._loop = asyncio.get_event_loop()

    def dispatch(self, event: Any) -> None:
        path = Path(event.src_path)
        if any(part in _IGNORE_DIRS for part in path.parts):
            return
        if path.suffix not in _WATCH_EXTENSIONS:
            return
        if event.event_type in ("modified", "created"):
            try:
                self._loop.call_soon_threadsafe(
                    self._queue.put_nowait, path
                )
            except Exception:
                pass


async def start_watch(watch_path: Path) -> None:
    """Start watching a directory for file changes."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        console.print("[error]watchdog не установлен. Запустите: pip install watchdog[/]")
        return

    queue: asyncio.Queue = asyncio.Queue()

    class _Handler(FileSystemEventHandler):
        def __init__(self):
            self._handler = _ChangeHandler(queue)

        def dispatch(self, event):
            self._handler.dispatch(event)

    observer = Observer()
    observer.schedule(_Handler(), str(watch_path), recursive=True)
    observer.start()

    console.print("[dim]Слежу за изменениями... (Ctrl+C для остановки)[/]\n")

    try:
        while True:
            try:
                path = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            # Debounce — drain queue for 0.5s
            await asyncio.sleep(0.5)
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            console.print(f"\n[cyan]Изменён:[/] {path}")
            await _analyze_change(path)

    except KeyboardInterrupt:
        console.print("\n[dim]Слежение остановлено[/]")
    finally:
        observer.stop()
        observer.join()


async def _analyze_change(path: Path) -> None:
    """Analyze a changed file and provide feedback."""
    from gib.git import GitIntegration
    from gib.providers import ChatMessage, OpenRouterClient
    from gib.prompts import PromptLibrary
    from gib.workspace import ProjectAnalyzer
    from rich.markdown import Markdown

    try:
        code = path.read_text(errors="ignore")[:8000]
    except Exception:
        return

    git = GitIntegration()
    diff = git.file_diff(str(path)) if git.is_git_repo else ""

    analyzer = ProjectAnalyzer()
    profile = analyzer.analyze()

    from gib.router import ModelRouter, TaskType
    router = ModelRouter()
    model = router.select_model(TaskType.WATCH)

    if diff:
        msgs = PromptLibrary.watch_analyze(diff[:4000], profile)
    else:
        msgs = [
            {"role": "system", "content": "Ты — GIB. Файл был сохранён. Кратко проанализируй его на наличие проблем (максимум 200 слов). Отвечай только на русском языке."},
            {"role": "user", "content": f"Файл: {path}\n\n```\n{code[:3000]}\n```"},
        ]

    try:
        client = OpenRouterClient()
        resp = await client.chat(
            [ChatMessage(**m) for m in msgs],
            model=model,
            max_tokens=512,
        )
        console.print(Markdown(resp.content))
        console.print(f"  [cost]{resp.cost_usd:.5f}$[/]  [dim]{resp.latency_ms}ms[/]\n")
    except Exception as e:
        console.print(f"[error]Ошибка анализа: {e}[/]")
