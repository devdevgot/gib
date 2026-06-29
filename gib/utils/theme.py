"""GIB terminal theme — Cursor / Claude Code inspired bright green UI."""
from __future__ import annotations

from rich.progress import SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.style import Style
from rich.theme import Theme

# ── Palette ───────────────────────────────────────────────────────────────────
GREEN = "#00FF87"           # яркий акцент (как Cursor agent)
GREEN_SOFT = "#3DFF8A"
GREEN_DIM = "#2EA043"
GREEN_MUTED = "#56D364"
BG_PANEL = "#0D1117"
TEXT = "#E6EDF3"
TEXT_DIM = "#8B949E"
TEXT_MUTED = "#6E7681"
BORDER = "#238636"
BORDER_BRIGHT = "#3FB950"
ERROR = "#FF7B72"
WARNING = "#E3B341"
BLUE_DIM = "#58A6FF"

GIB_THEME = Theme(
    {
        "primary": f"bold {GREEN}",
        "accent": GREEN,
        "brand": f"bold {GREEN}",
        "prompt": f"bold {GREEN}",
        "success": f"bold {GREEN}",
        "info": GREEN_SOFT,
        "error": f"bold {ERROR}",
        "warning": f"bold {WARNING}",
        "agent": f"bold {GREEN}",
        "model": TEXT_DIM,
        "cost": f"dim {GREEN_MUTED}",
        "dim": f"dim {TEXT_DIM}",
        "muted": f"dim {TEXT_MUTED}",
        "heading": f"bold {TEXT}",
        "border": BORDER_BRIGHT,
        "panel.title": f"bold {GREEN}",
    }
)

BANNER_ART = f"""\
[bold {GREEN}]  ██████╗ ██╗ ██████╗ [/]
[dim {TEXT_DIM}]  ██╔════╝ ██║██╔════╝ [/]
[bold {GREEN}]  ██║  ███╗██║██║  ███╗[/]
[dim {TEXT_DIM}]  ██║   ██║██║██║   ██║[/]
[bold {GREEN}]  ╚██████╔╝██║╚██████╔╝[/]
[dim {TEXT_DIM}]   ╚═════╝ ╚═╝ ╚═════╝ [/]"""

BANNER_TAGLINE = f"[dim {TEXT_DIM}]AI-операционная система для разработки[/]"


def prompt_prefix() -> str:
    return f"[bold {GREEN}]❯[/] "


def status_spinner_columns() -> list:
    """Колонки прогресса в стиле Claude Code."""
    return [
        SpinnerColumn(spinner_name="dots", style=Style(color=GREEN)),
        TextColumn("[progress.description]{task.description}", style=TEXT_DIM),
        TimeElapsedColumn(),
    ]
