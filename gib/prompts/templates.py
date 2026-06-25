"""All prompt templates for GIB agents."""
from __future__ import annotations

from gib.workspace.analyzer import ProjectProfile


SYSTEM_BASE = """You are GIB — an AI Development Operating System assistant.
You are embedded in a developer's terminal and help them write, fix, review, refactor, test, and document code.
Always respond with concrete, actionable output. Be precise and professional.
When providing code changes, always show the complete modified file or a clear diff.
Language: respond in the same language the user writes in (Russian if Russian, English if English).
"""


class PromptLibrary:
    """Centralized prompt template factory."""

    @staticmethod
    def _project_context(profile: ProjectProfile | None) -> str:
        if not profile:
            return ""
        return f"""
## Project context
- Language: {profile.language}
- Framework: {profile.framework}
- Package manager: {profile.package_manager}
- Git: {'yes' if profile.has_git else 'no'}
- Docker: {'yes' if profile.has_docker else 'no'}
- Tests: {'yes' if profile.has_tests else 'no'}
- Key directories: {', '.join(profile.key_dirs)}
"""

    @staticmethod
    def general(prompt: str, project: ProjectProfile | None = None, file_context: str = "") -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        file_section = f"\n## Relevant code\n```\n{file_context}\n```" if file_context else ""
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx},
            {"role": "user", "content": prompt + file_section},
        ]

    @staticmethod
    def review(code: str, project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + """
Your task: perform a thorough code review.
Analyze for:
1. Bugs and logic errors
2. Security vulnerabilities
3. Performance issues
4. Code quality (naming, duplication, complexity)
5. Architecture and design issues
6. Missing error handling
7. Test coverage gaps

Format your response as:
## Summary
## Critical Issues (must fix)
## Warnings (should fix)
## Suggestions (nice to have)
## Positive notes
"""},
            {"role": "user", "content": f"Review this code:\n\n```\n{code}\n```"},
        ]

    @staticmethod
    def fix(code: str, error: str = "", project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        error_section = f"\n\nError/issue:\n{error}" if error else ""
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + """
Your task: fix the code. 
- Identify the root cause
- Provide the fixed code
- Explain what was wrong and what you changed
Format: explanation first, then complete fixed code in a code block.
"""},
            {"role": "user", "content": f"Fix this code:\n\n```\n{code}\n```{error_section}"},
        ]

    @staticmethod
    def refactor(code: str, path: str = "", project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + """
Your task: refactor the code following SOLID principles, clean code, and best practices for the detected stack.
- Improve readability, maintainability, and performance
- Remove duplication
- Add proper type hints (if applicable)
- Preserve all existing functionality
Format: brief explanation of changes, then the refactored code in full.
"""},
            {"role": "user", "content": f"Refactor this code ({path}):\n\n```\n{code}\n```"},
        ]

    @staticmethod
    def test_generate(code: str, framework: str = "", project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        fw_hint = f"Use {framework} for tests." if framework else ""
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + f"""
Your task: write comprehensive tests for the given code.
{fw_hint}
Cover: happy paths, edge cases, error cases.
Output complete test file ready to run.
"""},
            {"role": "user", "content": f"Write tests for:\n\n```\n{code}\n```"},
        ]

    @staticmethod
    def docs(code: str, path: str = "", project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + """
Your task: generate comprehensive documentation.
Include:
- Module/file overview
- Function/class docstrings
- Parameters, return types, exceptions
- Usage examples
Output the fully documented code.
"""},
            {"role": "user", "content": f"Document this code ({path}):\n\n```\n{code}\n```"},
        ]

    @staticmethod
    def commit_message(diff: str) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_BASE + """
Your task: generate a git commit message following Conventional Commits format.
Format: <type>(<scope>): <short description>

[optional body]

[optional footer]

Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build
Keep the subject line under 72 characters. Be specific and clear.
Output ONLY the commit message, nothing else.
"""},
            {"role": "user", "content": f"Generate commit message for this diff:\n\n```diff\n{diff}\n```"},
        ]

    @staticmethod
    def doctor(codebase_summary: str, project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + """
Your task: perform a deep diagnostic of the codebase.
Find:
1. Potential bugs and runtime errors
2. Dead code (unused functions, variables, imports)
3. Duplicate code
4. Poor architecture patterns (anti-patterns, God objects, etc.)
5. Security vulnerabilities
6. Performance bottlenecks
7. Missing error handling
8. Hardcoded values that should be config

Format:
## Critical (fix now)
## Warnings (fix soon)  
## Tech debt (plan to fix)
## Quick wins
"""},
            {"role": "user", "content": f"Diagnose this codebase:\n\n{codebase_summary}"},
        ]

    @staticmethod
    def explain(code: str, path: str = "", project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + """
Your task: explain the code in detail.
Cover:
- What this module/file does
- How it works (architecture, flow)
- Key functions/classes and their purpose
- Dependencies and how they interact
- Any important patterns or decisions
Be thorough but clear. Use examples where helpful.
"""},
            {"role": "user", "content": f"Explain this code ({path}):\n\n```\n{code}\n```"},
        ]

    @staticmethod
    def watch_analyze(diff: str, project: ProjectProfile | None = None) -> list[dict]:
        ctx = PromptLibrary._project_context(project)
        return [
            {"role": "system", "content": SYSTEM_BASE + ctx + """
A file was just saved. Analyze the changes and provide:
1. Brief summary of what changed
2. Any issues introduced (bugs, style, performance)
3. Suggested improvements (if any)
4. Whether tests should be run
Keep it concise — this is live feedback.
"""},
            {"role": "user", "content": f"Analyze these file changes:\n\n```diff\n{diff}\n```"},
        ]
