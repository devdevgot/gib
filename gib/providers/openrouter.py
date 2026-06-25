"""OpenRouter API client — all models go through here."""
from __future__ import annotations

import time
from typing import AsyncIterator

import httpx
from pydantic import BaseModel

from gib.config import get_config
from gib.utils import get_logger

logger = get_logger("gib.providers.openrouter")


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    content: str
    model: str
    usage: UsageInfo = UsageInfo()
    cost_usd: float = 0.0
    latency_ms: int = 0


# Approximate costs per 1M tokens (input/output) for cost tracking
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "anthropic/claude-3.5-sonnet": (3.0, 15.0),
    "google/gemini-flash-1.5": (0.075, 0.3),
    "google/gemini-pro-1.5": (1.25, 5.0),
    "deepseek/deepseek-chat": (0.14, 0.28),
    "openai/gpt-4o": (5.0, 15.0),
    "openai/gpt-4o-mini": (0.15, 0.6),
    "meta-llama/llama-3.1-70b-instruct": (0.52, 0.75),
    "mistralai/mistral-large": (2.0, 6.0),
    "qwen/qwen-2.5-72b-instruct": (0.35, 0.4),
}


def _estimate_cost(model: str, usage: UsageInfo) -> float:
    """Estimate cost in USD from token usage."""
    costs = _MODEL_COSTS.get(model, (1.0, 3.0))
    input_cost = (usage.prompt_tokens / 1_000_000) * costs[0]
    output_cost = (usage.completion_tokens / 1_000_000) * costs[1]
    return round(input_cost + output_cost, 6)


class OpenRouterClient:
    """Async HTTP client for OpenRouter API."""

    def __init__(self) -> None:
        self._config = get_config()

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/gib-ai/gib",
            "X-Title": "GIB AI Development OS",
        }

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> ChatResponse:
        """Send a chat request and return a response."""
        resolved_model = model or self._config.models.default
        payload = {
            "model": resolved_model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        start = time.monotonic()
        attempt = 0
        last_error: Exception | None = None

        while attempt < self._config.openrouter.max_retries:
            try:
                async with httpx.AsyncClient(
                    timeout=self._config.openrouter.timeout
                ) as client:
                    resp = await client.post(
                        f"{self._config.openrouter.base_url}/chat/completions",
                        headers=self._get_headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                latency_ms = int((time.monotonic() - start) * 1000)
                choice = data["choices"][0]["message"]["content"]
                usage_raw = data.get("usage", {})
                usage = UsageInfo(
                    prompt_tokens=usage_raw.get("prompt_tokens", 0),
                    completion_tokens=usage_raw.get("completion_tokens", 0),
                    total_tokens=usage_raw.get("total_tokens", 0),
                )
                cost = _estimate_cost(resolved_model, usage)
                return ChatResponse(
                    content=choice,
                    model=resolved_model,
                    usage=usage,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                )

            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_error = e
                attempt += 1
                logger.warning("OpenRouter request failed (attempt %d): %s", attempt, e)
                if attempt >= self._config.openrouter.max_retries:
                    break

        raise RuntimeError(
            f"OpenRouter request failed after {self._config.openrouter.max_retries} attempts: {last_error}"
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        """Stream chat tokens."""
        resolved_model = model or self._config.models.default
        payload = {
            "model": resolved_model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(
            timeout=self._config.openrouter.timeout
        ) as client:
            async with client.stream(
                "POST",
                f"{self._config.openrouter.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        import json
                        try:
                            data = json.loads(chunk)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue
