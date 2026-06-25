"""Base agent — all agents inherit from this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from gib.providers import ChatMessage, ChatResponse, OpenRouterClient
from gib.utils import get_logger


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    output: str
    model: str = ""
    cost_usd: float = 0.0
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.output


class BaseAgent(ABC):
    """Abstract base for all GIB agents."""

    name: str = "base"

    def __init__(self) -> None:
        self._client = OpenRouterClient()
        self._logger = get_logger(f"gib.agents.{self.name}")

    async def _call(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> ChatResponse:
        """Call the LLM with given messages and model."""
        chat_messages = [ChatMessage(**m) for m in messages]
        return await self._client.chat(
            chat_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @abstractmethod
    async def run(self, **kwargs: Any) -> AgentResult:
        """Execute the agent's task."""
        ...
