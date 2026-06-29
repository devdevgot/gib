"""
GIB entrypoint wrapper.

Маршрутизация:
  gib улучши страницу дашборда     →  gib ask "улучши страницу дашборда"
  gib -y добавь кнопку экспорта    →  gib ask "добавь кнопку экспорта" --yes
  gib review / fix / ...           →  как есть
"""
from __future__ import annotations

import sys

_SUBCOMMANDS = {
    "review", "fix", "refactor", "commit", "doctor",
    "explain", "test", "docs", "watch", "chat", "ask", "resume", "set-key", "free",
}


def is_subcommand(token: str) -> bool:
    return token in _SUBCOMMANDS


def parse_freeform_flags(args: list[str]) -> tuple[list[str], bool]:
    """Выделяет -y/--yes из свободного запроса."""
    auto_yes = False
    tokens: list[str] = []
    for arg in args:
        if arg in ("-y", "--yes"):
            auto_yes = True
        else:
            tokens.append(arg)
    return tokens, auto_yes


def build_freeform_argv(argv: list[str]) -> list[str] | None:
    """Превращает `gib слово1 слово2` в argv для скрытой команды ask."""
    from gib.utils.request import join_prompt_args

    args = argv[1:]
    if not args:
        return None

    if args[0] in ("--help", "-h", "--version", "-v"):
        return None

    if is_subcommand(args[0]):
        return None

    tokens, auto_yes = parse_freeform_flags(args)
    prompt = join_prompt_args(tokens)
    if not prompt:
        return None

    new_argv = [argv[0], "ask", prompt]
    if auto_yes:
        new_argv.append("--yes")
    return new_argv


def main() -> None:
    from gib.cli.main import app

    rebuilt = build_freeform_argv(sys.argv)
    if rebuilt is not None:
        sys.argv = rebuilt

    app()


if __name__ == "__main__":
    main()
