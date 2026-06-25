"""Safe terminal command executor."""
from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path

from gib.utils import get_logger

logger = get_logger("gib.terminal")


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        return self.stdout or self.stderr


class TerminalExecutor:
    """Executes shell commands safely with timeout support."""

    def __init__(self, cwd: Path | None = None, timeout: int = 60) -> None:
        self.cwd = cwd or Path.cwd()
        self.timeout = timeout

    async def run(self, command: str, timeout: int | None = None) -> CommandResult:
        """Run a shell command asynchronously."""
        effective_timeout = timeout or self.timeout
        logger.debug("Running: %s", command)
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.cwd),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
            return CommandResult(
                command=command,
                returncode=proc.returncode or 0,
                stdout=stdout.decode(errors="replace").strip(),
                stderr=stderr.decode(errors="replace").strip(),
            )
        except asyncio.TimeoutError:
            logger.warning("Command timed out: %s", command)
            return CommandResult(
                command=command,
                returncode=124,
                stdout="",
                stderr=f"Command timed out after {effective_timeout}s",
            )
        except Exception as e:
            return CommandResult(
                command=command,
                returncode=1,
                stdout="",
                stderr=str(e),
            )

    def run_sync(self, command: str) -> CommandResult:
        """Synchronous wrapper for run()."""
        return asyncio.get_event_loop().run_until_complete(self.run(command))
