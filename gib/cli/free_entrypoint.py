"""
gibf — entrypoint для бесплатного режима GIB.

Использование:
  gibf добавь авторизацию
  gibf -y исправь опечатку в README
  gibf "исправь баги в auth.py"
"""
from __future__ import annotations

import sys


def main() -> None:
    from gib.cli.entrypoint import parse_freeform_flags

    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        sys.argv = [sys.argv[0], "free", "--help"]
        from gib.cli.main import app
        app()
        return

    tokens, auto_yes = parse_freeform_flags(args)
    from gib.utils.request import join_prompt_args
    prompt = join_prompt_args(tokens)
    if not prompt:
        sys.argv = [sys.argv[0], "free", "--help"]
        from gib.cli.main import app
        app()
        return

    sys.argv = [sys.argv[0], "free", prompt]
    if auto_yes:
        sys.argv.append("--yes")
    from gib.cli.main import app
    app()


if __name__ == "__main__":
    main()
