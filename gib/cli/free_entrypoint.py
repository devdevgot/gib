"""
gibf — entrypoint для бесплатного режима GIB.

Использование:
  gibf добавь авторизацию
  gibf "исправь баги в auth.py"

Всегда запускает FreeWorkflow (модели :free tier, без затрат).
"""
from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        sys.argv = [sys.argv[0], "free", "--help"]
        from gib.cli.main import app
        app()
        return

    # gibf слово1 слово2 → gib free "слово1 слово2"
    from gib.utils.request import join_prompt_args
    prompt = join_prompt_args(args)
    sys.argv = [sys.argv[0], "free", prompt]
    from gib.cli.main import app
    app()


if __name__ == "__main__":
    main()
