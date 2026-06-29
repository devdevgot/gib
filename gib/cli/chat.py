"""Interactive chat mode with project context and session memory."""
from __future__ import annotations

import asyncio
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel

from gib.utils.console import console


async def start_chat(*, resume: bool = True) -> None:
    """Start interactive GIB chat session."""
    from gib.config import get_config
    from gib.memory import MemoryStore
    from gib.memory.context import build_project_memory_context
    from gib.nodes.context_builder import node_context_builder
    from gib.core.state import make_initial_state
    from gib.providers import ChatMessage, OpenRouterClient
    from gib.router import ModelRouter
    from gib.workspace import ProjectAnalyzer

    project_path = str(Path.cwd().resolve())

    console.print(Panel.fit(
        "[bold cyan]GIB Chat[/]  [dim]Введите сообщение. 'exit' или Ctrl+C для выхода.[/]",
        border_style="cyan",
    ))

    analyzer = ProjectAnalyzer()
    profile = analyzer.analyze()

    console.print(
        f"  [dim]Проект:[/] [cyan]{profile.language}[/] / [cyan]{profile.framework}[/]  "
        f"[dim]Модель:[/] [model]{get_config().models.default}[/]\n"
    )

    router = ModelRouter()
    client = OpenRouterClient()
    memory = MemoryStore(project_root=project_path)

    # Загружаем контекст проекта (файлы + память)
    project_state = make_initial_state(
        user_request="chat session",
        workflow_type="chat",
        project_root=project_path,
    )
    project_state["project_context"] = {
        "root": project_path,
        "language": profile.language,
        "frameworks": [profile.framework] if profile.framework else [],
    }
    ctx_update = await node_context_builder(project_state)
    file_contents: dict[str, str] = ctx_update.get("file_contents", {})
    all_files = ctx_update.get("metadata", {}).get("all_project_files", [])
    memory_context = build_project_memory_context(memory, project_path, task_limit=10)

    file_index = "\n".join(f"  - {p}" for p in all_files[:80])
    if len(all_files) > 80:
        file_index += f"\n  ... и ещё {len(all_files) - 80} файлов"

    system_msg = f"""Ты — GIB, AI-ассистент для разработки программного обеспечения.
Ты помогаешь с проектом на {profile.language} / {profile.framework}.
Ключевые директории: {', '.join(profile.key_dirs[:6])}.
Проект содержит {len(all_files)} файлов в индексе.
Будь кратким, точным и давай готовые к использованию результаты. Приводи примеры кода где уместно.
ВАЖНО: всегда отвечай только на русском языке.

## Файлы проекта
{file_index}
"""
    if memory_context:
        system_msg += f"\n\n{memory_context}\n"

    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_msg)]

    session = memory.get_latest_session(project_path) if resume else None
    if session is None:
        session = memory.create_session(project_path=project_path)
        console.print(f"  [dim]Новая сессия #{session.id}[/]\n")
    else:
        prior = memory.get_session_messages(session.id)
        restored = 0
        for msg in prior:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
                restored += 1
        console.print(
            f"  [dim]Возобновлена сессия #{session.id} ({restored} сообщений)[/]\n"
        )

    total_cost = 0.0

    while True:
        try:
            console.print("[bold cyan]Gib >[/] ", end="")
            user_input = input("").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Чат завершён[/]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q", "bye", "выход", "стоп"):
            console.print("[dim]До свидания![/]")
            break

        # Подмешиваем содержимое упомянутых файлов
        user_content = user_input
        for path in all_files:
            if path in user_input and path in file_contents:
                snippet = file_contents[path][:4000]
                user_content += f"\n\n### {path}\n```\n{snippet}\n```"
                break

        messages.append(ChatMessage(role="user", content=user_content))
        memory.append_session_message(session.id, "user", user_input)

        task_type, model = router.route(user_input)

        try:
            console.print(f"  [dim]({model})[/]")
            resp = await client.chat(
                messages,
                model=model,
                temperature=0.3,
                max_tokens=4096,
            )

            messages.append(ChatMessage(role="assistant", content=resp.content))
            memory.append_session_message(session.id, "assistant", resp.content)
            total_cost += resp.cost_usd

            memory.save_task(
                task_type="chat",
                prompt=user_input[:8000],
                model_used=resp.model,
                result_summary=resp.content[:50_000],
                cost_usd=resp.cost_usd,
                project_path=project_path,
                status="completed",
            )

            console.print()
            console.print(Markdown(resp.content))
            console.print(
                f"\n  [стоимость]${resp.cost_usd:.5f}[/]  "
                f"[dim]{resp.latency_ms}ms  ·  всего ${total_cost:.4f}[/]\n"
            )

        except Exception as e:
            console.print(f"[error]✗ {e}[/]")
            messages.pop()
