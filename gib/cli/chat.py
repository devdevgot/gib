"""Interactive chat mode with project context."""
from __future__ import annotations

import asyncio
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel

from gib.utils.console import console


async def start_chat() -> None:
    """Start interactive GIB chat session."""
    from gib.config import get_config
    from gib.memory import MemoryStore
    from gib.providers import ChatMessage, OpenRouterClient
    from gib.router import ModelRouter, TaskType
    from gib.workspace import ProjectAnalyzer

    console.print(Panel.fit(
        "[bold cyan]GIB Chat[/]  [dim]Type your message. 'exit' or Ctrl+C to quit.[/]",
        border_style="cyan",
    ))

    # Analyze project
    analyzer = ProjectAnalyzer()
    profile = analyzer.analyze()

    console.print(
        f"  [dim]Project:[/] [cyan]{profile.language}[/] / [cyan]{profile.framework}[/]  "
        f"[dim]Model:[/] [model]{get_config().models.default}[/]\n"
    )

    router = ModelRouter()
    client = OpenRouterClient()
    memory = MemoryStore()

    # Build system message
    system_msg = f"""You are GIB — an AI Development Operating System.
You are helping with a {profile.language} / {profile.framework} project.
Key directories: {', '.join(profile.key_dirs[:6])}.
Be concise, precise, and actionable. Provide code examples when relevant.
"""

    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_msg)]
    session = memory.create_session(project_path=str(Path.cwd()))
    total_cost = 0.0

    while True:
        try:
            console.print("[bold cyan]Gib >[/] ", end="")
            user_input = input("").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Chat ended[/]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q", "bye"):
            console.print("[dim]Goodbye![/]")
            break

        messages.append(ChatMessage(role="user", content=user_input))
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

            console.print()
            console.print(Markdown(resp.content))
            console.print(
                f"\n  [cost]${resp.cost_usd:.5f}[/]  "
                f"[dim]{resp.latency_ms}ms  ·  total ${total_cost:.4f}[/]\n"
            )

        except Exception as e:
            console.print(f"[error]✗ {e}[/]")
            # Remove the user message from history on failure
            messages.pop()
