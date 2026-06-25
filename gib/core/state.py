"""GIB Global State — единое состояние для всех LangGraph графов.

Используем TypedDict + Annotated reducers для корректного накопления данных
в параллельных ветках.
"""
from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict

from gib.core.types import ApprovalStatus, ReviewVerdict, SubTask, PatchFile, SecurityIssue, AgentOutput


def _append(a: list, b: list) -> list:
    """Reducer: добавить новые элементы к существующим."""
    return a + b


def _sum_float(a: float, b: float) -> float:
    return a + b


def _sum_int(a: int, b: int) -> int:
    return a + b


def _merge_dict(a: dict, b: dict) -> dict:
    return {**a, **b}


class GibState(TypedDict, total=False):
    """
    Единое состояние GIB Pipeline.
    Все поля total=False — узлы возвращают только то, что изменяют.
    
    Annotated[X, reducer] — LangGraph использует reducer для слияния значений
    из параллельных веток и последовательных обновлений.
    """

    # ── Входные данные ──────────────────────────────────────────────────────
    user_request: str                          # Исходная задача пользователя
    workflow_type: str                         # WorkflowType enum value
    target_paths: list[str]                    # Файлы/папки для обработки
    error_input: str                           # Текст ошибки (для bugfix)

    # ── Анализ проекта (ProjectAnalyzer) ────────────────────────────────────
    project_context: dict[str, Any]            # Язык, фреймворк, пакетный менеджер
    repository_context: dict[str, Any]         # Git статус, последние коммиты
    detected_stack: dict[str, Any]             # Обнаруженный стек технологий

    # ── Контекст (ContextBuilder) ────────────────────────────────────────────
    file_contents: dict[str, str]              # path → содержимое файла
    relevant_files: list[str]                  # Список релевантных файлов
    readme_content: str
    dependencies_raw: str                      # Содержимое requirements/package.json

    # ── Планирование (TaskPlanner) ───────────────────────────────────────────
    execution_plan: str                        # Текстовый план от Claude
    subtasks: list[SubTask]                    # Структурированные подзадачи
    current_step: str                          # Текущий шаг пайплайна
    selected_models: dict[str, str]            # role → model_id

    # ── Supervisor ───────────────────────────────────────────────────────────
    supervisor_decision: str                   # continue / retry / abort / finish
    completed_agents: Annotated[list[str], _append]    # Выполненные агенты
    failed_agents: Annotated[list[str], _append]

    # ── Параллельные агенты ──────────────────────────────────────────────────
    architecture_result: str                   # Claude: архитектурный план
    code_result: str                           # GPT: написанный код
    research_result: str                       # Gemini: документация + best practices
    agent_outputs: Annotated[list[AgentOutput], _append]  # Все выходы агентов

    # ── Ревью ────────────────────────────────────────────────────────────────
    review_result: str                         # Полный текст ревью
    review_verdict: str                        # ReviewVerdict enum value
    review_comments: Annotated[list[str], _append]  # Комментарии ревьюера
    review_iteration: int                      # Текущая итерация (макс 2)
    max_review_iterations: int

    # ── Безопасность (Security) ──────────────────────────────────────────────
    security_issues: Annotated[list[SecurityIssue], _append]
    security_passed: bool                      # True если критических проблем нет

    # ── Тесты ───────────────────────────────────────────────────────────────
    tests: str                                 # Сгенерированные тесты
    test_framework: str                        # pytest / jest / etc

    # ── Документация ────────────────────────────────────────────────────────
    documentation: str

    # ── Patch / Diff ─────────────────────────────────────────────────────────
    patch_files: list[PatchFile]               # Список изменённых файлов
    git_diff: str                              # Итоговый unified diff

    # ── Human Approval ───────────────────────────────────────────────────────
    approval_status: str                       # ApprovalStatus enum value
    approval_summary: str                      # Что будет изменено (для показа)

    # ── Git ──────────────────────────────────────────────────────────────────
    commit_message: str
    branch_name: str
    pr_description: str

    # ── Метрики (суммируются через Annotated reducers) ──────────────────────
    total_cost_usd: Annotated[float, _sum_float]
    total_latency_ms: Annotated[int, _sum_int]
    models_used: Annotated[list[str], _append]   # Все использованные модели
    token_usage: Annotated[dict[str, int], _merge_dict]

    # ── Логи ────────────────────────────────────────────────────────────────
    logs: Annotated[list[str], _append]          # Лог событий пайплайна
    warnings: Annotated[list[str], _append]

    # ── Финал ────────────────────────────────────────────────────────────────
    final_output: str
    success: bool
    error_message: str                         # Ошибка если success=False

    # ── Metadata ─────────────────────────────────────────────────────────────
    metadata: dict[str, Any]


def make_initial_state(
    user_request: str,
    workflow_type: str,
    target_paths: list[str] | None = None,
    error_input: str = "",
) -> GibState:
    """Создаёт начальное состояние с безопасными дефолтами."""
    return GibState(
        user_request=user_request,
        workflow_type=workflow_type,
        target_paths=target_paths or [],
        error_input=error_input,
        project_context={},
        repository_context={},
        detected_stack={},
        file_contents={},
        relevant_files=[],
        readme_content="",
        dependencies_raw="",
        execution_plan="",
        subtasks=[],
        current_step="init",
        selected_models={},
        supervisor_decision="continue",
        completed_agents=[],
        failed_agents=[],
        architecture_result="",
        code_result="",
        research_result="",
        agent_outputs=[],
        review_result="",
        review_verdict=ReviewVerdict.APPROVED.value,
        review_comments=[],
        review_iteration=1,
        max_review_iterations=2,
        security_issues=[],
        security_passed=True,
        tests="",
        test_framework="",
        documentation="",
        patch_files=[],
        git_diff="",
        approval_status=ApprovalStatus.PENDING.value,
        approval_summary="",
        commit_message="",
        branch_name="",
        pr_description="",
        total_cost_usd=0.0,
        total_latency_ms=0,
        models_used=[],
        token_usage={},
        logs=[],
        warnings=[],
        final_output="",
        success=False,
        error_message="",
        metadata={},
    )
