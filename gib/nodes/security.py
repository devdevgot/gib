"""Node: Security Scanner — статический анализ + LLM для сложных случаев.

Проверяет: SQL Injection, XSS, Secrets, JWT, Hardcoded Keys.
Использует только статику где возможно, LLM только для сложных паттернов.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from gib.core.container import Container
from gib.core.state import GibState
from gib.core.types import SecurityIssue
from gib.prompts.locale import RUSSIAN_ONLY
from gib.utils import get_logger

logger = get_logger("gib.nodes.security")

_SECURITY_LLM_SYSTEM = f"""\
Ты — инженер по безопасности. Проверь сгенерированный код на уязвимости.

Ищи: секреты в коде, SQL-инъекции, XSS, обход авторизации, слабую криптографию,
инъекции команд, небезопасную десериализацию.

Верни ТОЛЬКО JSON-массив объектов:
[{{"severity": "critical|high|medium|low", "category": "...", "file": "...", "line": 0, "description": "...", "recommendation": "..."}}]

Если проблем нет — верни [].

{RUSSIAN_ONLY}
"""

# ── Статические правила ──────────────────────────────────────────────────────

@dataclass
class _StaticRule:
    pattern: str
    severity: str
    category: str
    description: str
    recommendation: str


_STATIC_RULES: list[_StaticRule] = [
    _StaticRule(
        pattern=r"(?i)(password|passwd|pwd|secret|api_key|apikey|token|private_key)\s*=\s*['\"][^'\"]{6,}['\"]",
        severity="critical",
        category="secrets",
        description="Обнаружен захардкоженный секрет или учётные данные",
        recommendation="Вынесите в переменные окружения или менеджер секретов",
    ),
    _StaticRule(
        pattern=r"(?i)execute\s*\(\s*['\"].*?\%[sd].*?['\"].*?\%|execute\s*\(\s*f['\"].*?\{.*?\}",
        severity="critical",
        category="sql_injection",
        description="Возможная SQL-инъекция через форматирование строк",
        recommendation="Используйте параметризованные запросы или ORM",
    ),
    _StaticRule(
        pattern=r"(?i)innerHTML\s*=|document\.write\s*\(|eval\s*\(",
        severity="high",
        category="xss",
        description="Возможная XSS через небезопасную работу с DOM",
        recommendation="Используйте textContent, DOMPurify или экранирование шаблонов",
    ),
    _StaticRule(
        pattern=r"(?i)jwt\.decode\([^,]+,?\s*(?:options\s*=\s*\{[^}]*verify\s*:\s*false|algorithms\s*=\s*\[[\s'\"]*none[\s'\"]*\])",
        severity="critical",
        category="jwt",
        description="Отключена проверка JWT",
        recommendation="Всегда проверяйте подписи JWT",
    ),
    _StaticRule(
        pattern=r"(?i)verify\s*=\s*False|ssl_verify\s*=\s*False|verify_ssl\s*=\s*False",
        severity="high",
        category="ssl",
        description="Отключена проверка SSL",
        recommendation="Никогда не отключайте проверку SSL в продакшене",
    ),
    _StaticRule(
        pattern=r"(?i)subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True",
        severity="high",
        category="command_injection",
        description="Риск инъекции команд через shell=True",
        recommendation="Используйте shell=False и передавайте аргументы списком",
    ),
    _StaticRule(
        pattern=r"(?i)pickle\.loads?\s*\(",
        severity="high",
        category="deserialization",
        description="Небезопасная десериализация через pickle",
        recommendation="Используйте JSON или криптографически подписанные форматы",
    ),
    _StaticRule(
        pattern=r"(?i)md5\s*\(|hashlib\.md5|hashlib\.sha1",
        severity="medium",
        category="weak_crypto",
        description="Слабая криптографическая хеш-функция",
        recommendation="Используйте SHA-256 или сильнее (hashlib.sha256)",
    ),
    _StaticRule(
        pattern=r"(?i)random\.random\(\)|random\.randint\(",
        severity="low",
        category="weak_random",
        description="Некриптографический random для потенциально чувствительных данных",
        recommendation="Используйте модуль secrets для криптографически стойкой случайности",
    ),
    _StaticRule(
        pattern=r"(?i)0\.0\.0\.0|ALLOWED_HOSTS\s*=\s*\[[\s'\"]*\*[\s'\"]*\]",
        severity="medium",
        category="network",
        description="Слишком широкие сетевые привязки или CORS",
        recommendation="Ограничьте конкретными хостами в продакшене",
    ),
]


def _scan_content(content: str, file_path: str) -> list[SecurityIssue]:
    """Применяет статические правила к содержимому файла."""
    issues: list[SecurityIssue] = []
    lines = content.splitlines()

    for rule in _STATIC_RULES:
        for line_no, line in enumerate(lines, start=1):
            if re.search(rule.pattern, line):
                issues.append(SecurityIssue(
                    severity=rule.severity,
                    category=rule.category,
                    file=file_path,
                    line=line_no,
                    description=rule.description,
                    recommendation=rule.recommendation,
                ))
                break  # одно срабатывание на правило/файл

    return issues


def _parse_llm_security_issues(raw: str) -> list[SecurityIssue]:
    """Парсит JSON-ответ LLM security review."""
    content = raw.strip()
    if "```" in content:
        match = re.search(r"```(?:json)?\s*(\[[\s\S]+?\])\s*```", content)
        if match:
            content = match.group(1)
    match = re.search(r"\[[\s\S]*\]", content)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    issues: list[SecurityIssue] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        issues.append(SecurityIssue(
            severity=str(item.get("severity", "medium")),
            category=str(item.get("category", "llm_review")),
            file=str(item.get("file", "<сгенерированный_код>")),
            line=int(item.get("line", 0) or 0),
            description=str(item.get("description", ""))[:500],
            recommendation=str(item.get("recommendation", ""))[:500],
        ))
    return issues


async def _llm_security_review(state: GibState, model: str) -> list[SecurityIssue]:
    """LLM-проверка безопасности для free workflow."""
    code = state.get("code_result", "")
    if not code:
        return []

    relevant = state.get("relevant_files", [])[:5]
    file_contents = state.get("file_contents", {})
    snippets = []
    for path in relevant:
        content = file_contents.get(path, "")
        if content:
            snippets.append(f"### {path}\n```\n{content[:4000]}\n```")

    prompt = f"""## Задача
{state.get("user_request", "")}

## Сгенерированный код
{code[:12000]}

## Контекст проекта
{chr(10).join(snippets) if snippets else "(нет дополнительных файлов)"}
"""

    container = Container.instance()
    from gib.providers import ChatMessage

    resp = await container.openrouter_client().chat(
        [
            ChatMessage(role="system", content=_SECURITY_LLM_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        temperature=0.0,
        max_tokens=2048,
    )
    return _parse_llm_security_issues(resp.content)


async def node_security(state: GibState) -> dict:
    """
    LangGraph Node: статический анализ безопасности.
    
    Не использует LLM — только регулярные выражения.
    """
    file_contents = state.get("file_contents", {})
    code_result = state.get("code_result", "")

    all_issues: list[SecurityIssue] = []

    # Сканируем существующие файлы проекта
    for file_path, content in file_contents.items():
        issues = _scan_content(content, file_path)
        all_issues.extend(issues)

    # Сканируем новый код от разработчика
    if code_result:
        issues = _scan_content(code_result, "<сгенерированный_код>")
        all_issues.extend(issues)

    security_model = state.get("selected_models", {}).get("security")
    if security_model:
        try:
            llm_issues = await _llm_security_review(state, security_model)
            all_issues.extend(llm_issues)
            logger.info("[security] LLM review (%s): %d issues", security_model, len(llm_issues))
        except Exception as e:
            logger.warning("[security] LLM review failed: %s", e)

    # Определяем прошёл ли скан
    critical_count = sum(1 for i in all_issues if i.severity == "critical")
    high_count = sum(1 for i in all_issues if i.severity == "high")
    security_passed = critical_count == 0  # блокируем только на critical

    severity_counts = {
        "critical": critical_count,
        "high": high_count,
        "medium": sum(1 for i in all_issues if i.severity == "medium"),
        "low": sum(1 for i in all_issues if i.severity == "low"),
    }

    logger.info(
        "[security] Скан завершён: %d issues (critical=%d, high=%d)",
        len(all_issues), critical_count, high_count
    )

    log_msg = (
        f"[Security] {'ПРОЙДЕН' if security_passed else 'ЗАБЛОКИРОВАН'} — "
        f"critical={critical_count}, high={high_count}, "
        f"medium={severity_counts['medium']}, low={severity_counts['low']}"
    )

    warnings: list[str] = []
    if not security_passed:
        warnings.append(
            f"⚠️ Найдено критических проблем безопасности: {critical_count}. "
            "Исправьте перед применением изменений."
        )

    return {
        "security_issues": all_issues,
        "security_passed": security_passed,
        "current_step": "security_scanned",
        "logs": [log_msg],
        "warnings": warnings,
        "metadata": {"security_severity_counts": severity_counts},
    }
