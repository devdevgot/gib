"""Git integration module."""
from .executor import GitCommandResult, execute_git_intent
from .integration import GitIntegration
from .intent import GitAction, GitIntent, parse_git_intent

__all__ = [
    "GitAction",
    "GitCommandResult",
    "GitIntegration",
    "GitIntent",
    "execute_git_intent",
    "parse_git_intent",
]
