"""Tests for security LLM parsing."""
from gib.nodes.security import _parse_llm_security_issues


def test_parse_llm_security_issues_json():
    raw = """```json
[
  {
    "severity": "high",
    "category": "secrets",
    "file": "app.py",
    "line": 10,
    "description": "Hardcoded API key",
    "recommendation": "Use env vars"
  }
]
```"""
    issues = _parse_llm_security_issues(raw)
    assert len(issues) == 1
    assert issues[0].severity == "high"
    assert issues[0].file == "app.py"
