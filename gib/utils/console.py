"""Shared Rich console instance."""
from rich.console import Console

from gib.utils.theme import GIB_THEME

console = Console(theme=GIB_THEME, highlight=False, soft_wrap=True)
