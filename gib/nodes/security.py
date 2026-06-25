"""Node: Security Scanner — статический анализ + LLM для сложных случаев.

Проверяет: SQL Injection, XSS, Secrets, JWT, Hardcoded Keys.
Использует только статику где возможно, LLM только для сложных паттернов.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from gib.core.state import GibState
from gib.core.types import SecurityIssue
from gib.utils import get_logger

logger = get_logger("gib.nodes.security")

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
        description="Hardcoded secret/credential detected",
        recommendation="Move to environment variables or secrets manager",
    ),
    _StaticRule(
        pattern=r"(?i)execute\s*\(\s*['\"].*?\%[sd].*?['\"].*?\%|execute\s*\(\s*f['\"].*?\{.*?\}",
        severity="critical",
        category="sql_injection",
        description="Potential SQL Injection via string formatting",
        recommendation="Use parameterized queries or ORM",
    ),
    _StaticRule(
        pattern=r"(?i)innerHTML\s*=|document\.write\s*\(|eval\s*\(",
        severity="high",
        category="xss",
        description="Potential XSS via unsafe DOM manipulation",
        recommendation="Use textContent, DOMPurify, or template escaping",
    ),
    _StaticRule(
        pattern=r"(?i)jwt\.decode\([^,]+,?\s*(?:options\s*=\s*\{[^}]*verify\s*:\s*false|algorithms\s*=\s*\[[\s'\"]*none[\s'\"]*\])",
        severity="critical",
        category="jwt",
        description="JWT verification disabled",
        recommendation="Always verify JWT signatures",
    ),
    _StaticRule(
        pattern=r"(?i)verify\s*=\s*False|ssl_verify\s*=\s*False|verify_ssl\s*=\s*False",
        severity="high",
        category="ssl",
        description="SSL verification disabled",
        recommendation="Never disable SSL verification in production",
    ),
    _StaticRule(
        pattern=r"(?i)subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True",
        severity="high",
        category="command_injection",
        description="Shell command injection risk via shell=True",
        recommendation="Use shell=False and pass arguments as list",
    ),
    _StaticRule(
        pattern=r"(?i)pickle\.loads?\s*\(",
        severity="high",
        category="deserialization",
        description="Unsafe deserialization with pickle",
        recommendation="Use JSON or cryptographically signed formats",
    ),
    _StaticRule(
        pattern=r"(?i)md5\s*\(|hashlib\.md5|hashlib\.sha1",
        severity="medium",
        category="weak_crypto",
        description="Weak cryptographic hash function",
        recommendation="Use SHA-256 or stronger (hashlib.sha256)",
    ),
    _StaticRule(
        pattern=r"(?i)random\.random\(\)|random\.randint\(",
        severity="low",
        category="weak_random",
        description="Non-cryptographic random for potentially sensitive use",
        recommendation="Use secrets module for security-sensitive randomness",
    ),
    _StaticRule(
        pattern=r"(?i)0\.0\.0\.0|ALLOWED_HOSTS\s*=\s*\[[\s'\"]*\*[\s'\"]*\]",
        severity="medium",
        category="network",
        description="Overly permissive network binding or CORS",
        recommendation="Restrict to specific hosts in production",
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
        issues = _scan_content(code_result, "<generated_code>")
        all_issues.extend(issues)

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
        f"[Security] {'PASSED' if security_passed else 'BLOCKED'} — "
        f"critical={critical_count}, high={high_count}, "
        f"medium={severity_counts['medium']}, low={severity_counts['low']}"
    )

    warnings: list[str] = []
    if not security_passed:
        warnings.append(
            f"⚠️ {critical_count} critical security issues found! Fix before applying changes."
        )

    return {
        "security_issues": all_issues,
        "security_passed": security_passed,
        "current_step": "security_scanned",
        "logs": [log_msg],
        "warnings": warnings,
        "metadata": {"security_severity_counts": severity_counts},
    }
