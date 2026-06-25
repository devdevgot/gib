"""
GIB entrypoint wrapper.
Routes `gib "free prompt"` to `gib ask "free prompt"` internally,
while proper subcommands (review, fix, etc.) are passed through as-is.
"""
from __future__ import annotations

import sys


_SUBCOMMANDS = {
    "review", "fix", "refactor", "commit", "doctor",
    "explain", "test", "docs", "watch", "chat", "ask",
    "--help", "-h", "--version", "-v",
}


def main() -> None:
    args = sys.argv[1:]

    # No args → show help
    if not args:
        from gib.cli.main import app
        app()
        return

    first = args[0]

    # Known subcommand or flag → pass through unchanged
    if first in _SUBCOMMANDS or first.startswith("-"):
        from gib.cli.main import app
        app()
        return

    # Otherwise treat as a free-form prompt → inject 'ask' subcommand
    sys.argv = [sys.argv[0], "ask"] + args
    from gib.cli.main import app
    app()


if __name__ == "__main__":
    main()
