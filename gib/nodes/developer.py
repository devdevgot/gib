"""Node: Developer Agent — пишет код по архитектурному плану."""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import AgentOutput, AgentRole, TaskType
from gib.prompts.locale import RUSSIAN_ONLY
from gib.utils import get_logger

logger = get_logger("gib.nodes.developer")

_DEVELOPER_SYSTEM = f"""\
Ты — ведущий инженер-разработчик. Пишешь production-качественный код.

Правила:
- Пиши полный рабочий код — не псевдокод и не примеры
- Следуй стилю и соглашениям существующего кода
- Добавляй корректную обработку ошибок
- Пиши самодокументируемый код с понятными именами
- Добавляй docstring для публичных функций
- Никогда не оставляй TODO — реализуй всё полностью
- При изменении файла показывай ПОЛНЫЙ изменённый файл (не только diff)
- Используй ТОЧНЫЕ пути из раздела «Релевантные файлы» — не выдумывай пути

Формат ответа:
1. Краткое объяснение подхода (2–5 строк) на русском языке
2. Каждый файл отдельным блоком:

### path/to/file.py
```python
<полное содержимое файла>
```

КРИТИЧНО: путь после ### должен точно совпадать с одним из путей в «Релевантные файлы»
или быть новым путём, логичным для структуры проекта.

{RUSSIAN_ONLY}
"""

_RETRY_SUFFIX = """\

## ⚠️ Замечания ревьюера (ОБЯЗАТЕЛЬНО ИСПРАВИТЬ ВСЕ)
{review_comments}

Ревьюер отклонил предыдущую реализацию. Исправь ВСЕ перечисленные проблемы.
"""


def _build_developer_prompt(state: GibState) -> str:
    arch = state.get("architecture_result", "")
    relevant_files: list[str] = state.get("relevant_files", [])
    file_contents: dict[str, str] = state.get("file_contents", {})
    iteration = state.get("review_iteration", 1)
    review = state.get("review_result", "")
    session_context = state.get("session_context", "")
    comments = state.get("review_comments", [])

    if relevant_files:
        files_list = "\n".join(f"  - {f}" for f in relevant_files)
        relevant_section = (
            f"\n## Релевантные файлы (используй ТОЧНЫЕ пути в заголовках ###)\n{files_list}"
        )
    else:
        relevant_section = ""

    file_context = ""
    for path in relevant_files:
        content = file_contents.get(path, "")
        if not content:
            continue
        preview = content[:6000 if state.get("metadata", {}).get("free_mode") else 12000]
        if len(content) > 12000:
            preview += f"\n\n... [обрезано на 12000 символов, полный файл {len(content)} символов]"
        file_context += f"\n### {path}\n```\n{preview}\n```\n"

    if not file_context and file_contents:
        for path, content in list(file_contents.items())[:15]:
            preview = content[:4000]
            file_context += f"\n### {path}\n```\n{preview}\n```\n"

    parts = [
        f"## Задача\n{state.get('user_request', '')}",
        f"\n{session_context}" if session_context else "",
        relevant_section,
        f"\n## Архитектурный план\n{arch}" if arch else "",
        f"\n## Существующий код{file_context}" if file_context else "",
    ]

    prompt = "\n".join(p for p in parts if p)

    if iteration > 1 and (review or comments):
        review_text = "\n".join(comments) if comments else review[:2000]
        prompt += _RETRY_SUFFIX.format(review_comments=review_text)

    return prompt


async def node_developer(state: GibState) -> dict:
    """LangGraph Node: пишет реализацию."""
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    model = state.get("selected_models", {}).get(
        AgentRole.DEVELOPER.value,
        router.select_model(TaskType.DEVELOPMENT)
    )
    prompt = _build_developer_prompt(state)
    iteration = state.get("review_iteration", 1)

    logger.info("[developer] Пишу код, итерация=%d, модель=%s", iteration, model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_DEVELOPER_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.15,
        max_tokens=8192,
    )

    output = AgentOutput(
        role=AgentRole.DEVELOPER,
        model_id=resp.model,
        content=resp.content,
        cost_usd=resp.cost_usd,
        latency_ms=resp.latency_ms,
        metadata={"iteration": iteration},
    )

    logger.info("[developer] Готово: %d chars, cost=$%.4f", len(resp.content), resp.cost_usd)

    return {
        "code_result": resp.content,
        "agent_outputs": [output],
        "completed_agents": [AgentRole.DEVELOPER.value],
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[Developer] Итерация {iteration}, модель={resp.model}, стоимость=${resp.cost_usd:.4f}"],
    }
