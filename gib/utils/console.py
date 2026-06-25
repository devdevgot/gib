"""Shared Rich console instance."""
from rich.console import Console
from rich.theme import Theme

_THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "agent": "bold magenta",
        "model": "bold blue",
        "cost": "dim yellow",
        "dim": "dim",
        "heading": "bold white",
    }
)

console = Console(theme=_THEME, highlight=False)
