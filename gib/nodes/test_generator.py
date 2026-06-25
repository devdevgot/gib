"""Node: Test Generator — автоматически определяет фреймворк и генерирует тесты."""
from __future__ import annotations

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import TaskType
from gib.utils import get_logger

logger = get_logger("gib.nodes.test_generator")

_FRAMEWORK_DETECT: dict[str, list[str]] = {
    "pytest": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"],
    "jest": ["package.json"],
    "vitest": ["vite.config", "vitest.config"],
    "phpunit": ["composer.json", "phpunit.xml"],
    "rspec": ["Gemfile", "spec/"],
    "go test": ["go.mod"],
    "cargo test": ["Cargo.toml"],
    "junit": ["pom.xml", "build.gradle"],
}

_FRAMEWORK_SIGNATURES: dict[str, list[str]] = {
    "pytest": ["pytest", "unittest", "import pytest"],
    "jest": ['"jest"', '"@jest/core"', '"jest-circus"'],
    "vitest": ["vitest", '"vitest"'],
}

_TEST_SYSTEM = """\
You are a Senior Test Engineer. Write comprehensive, production-quality tests.

Rules:
- Write tests that actually test behavior, not implementation
- Cover: happy path, edge cases, error cases, boundary values
- Use proper test isolation (mocks, fixtures, dependency injection)
- Name tests descriptively: test_<action>_<condition>_<expected_result>
- Aim for 80%+ coverage of the new code
- Include integration tests where appropriate

Format:
### <filename>
```<language>
<test code>
```
"""


def _detect_test_framework(state: GibState) -> str:
    """Определяет тестовый фреймворк по файлам проекта."""
    from pathlib import Path
    root = Path(state.get("project_context", {}).get("root", "."))
    deps = state.get("dependencies_raw", "").lower()
    file_names = [f.lower() for f in state.get("file_contents", {}).keys()]

    # По зависимостям
    for fw, _ in _FRAMEWORK_DETECT.items():
        for sig in _FRAMEWORK_SIGNATURES.get(fw, [fw.lower()]):
            if sig.lower() in deps:
                return fw

    # По файлам
    lang = state.get("project_context", {}).get("language", "")
    if "python" in lang.lower():
        return "pytest"
    if "javascript" in lang.lower() or "typescript" in lang.lower():
        return "jest"
    if "go" in lang.lower():
        return "go test"
    if "rust" in lang.lower():
        return "cargo test"
    if "java" in lang.lower():
        return "junit"
    if "ruby" in lang.lower():
        return "rspec"
    if "php" in lang.lower():
        return "phpunit"

    return "pytest"  # fallback


def _build_test_prompt(state: GibState, framework: str) -> str:
    code = state.get("code_result", "")
    arch = state.get("architecture_result", "")
    existing_files = state.get("file_contents", {})

    # Ищем существующие тестовые файлы для примера стиля
    test_examples = ""
    for path, content in existing_files.items():
        if "test" in path.lower() or "spec" in path.lower():
            test_examples += f"\n### Existing test (style reference): {path}\n{content[:1000]}\n"
            break

    parts = [
        f"## Task\n{state.get('user_request', '')}",
        f"\n## Test Framework: {framework}",
        f"\n## Code to Test\n{code[:6000]}" if code else "",
        f"\n## Architecture\n{arch[:1500]}" if arch else "",
        test_examples,
        "\n## Write comprehensive tests for all the above code.",
    ]

    return "\n".join(p for p in parts if p)


async def node_test_generator(state: GibState) -> dict:
    """
    LangGraph Node: генерирует тесты.
    """
    container = Container.instance()
    client = container.openrouter_client()
    router = container.model_router()

    from gib.providers import ChatMessage
    framework = _detect_test_framework(state)
    model = router.select_model(TaskType.TESTING)
    prompt = _build_test_prompt(state, framework)

    logger.info("[test_generator] Framework=%s, модель=%s", framework, model)

    resp = await client.chat(
        [
            ChatMessage(role="system", content=_TEST_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.2,
        max_tokens=6144,
    )

    logger.info("[test_generator] Готово: %d chars", len(resp.content))

    return {
        "tests": resp.content,
        "test_framework": framework,
        "current_step": "tests_generated",
        "total_cost_usd": resp.cost_usd,
        "total_latency_ms": resp.latency_ms,
        "models_used": [resp.model],
        "logs": [f"[TestGenerator] {framework} tests generated with {resp.model}"],
    }
