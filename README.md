# GIB — AI Development Operating System

> Терминальный AI-оркестратор для разработки. Аналог Cursor Agent и Claude Code — работает в терминале, поддерживает любые модели через OpenRouter, управляет разработкой через граф агентов на LangGraph.

---

## Быстрый старт

```bash
pipx install git+https://github.com/devdevgot/gib.git
gib                              # первый запуск попросит API ключ
```

**Обновление до последней версии:**

```bash
# Удалить старую pip-установку, если была (частая причина версии 0.1.0)
pip uninstall gib -y 2>/dev/null || true

pipx install --force git+https://github.com/devdevgot/gib.git@main
hash -r   # bash: обновить кэш PATH
gib --version   # должно быть gib 0.1.2
```

Если версия всё ещё старая — проверьте, какой бинарник запускается:

```bash
which -a gib
pipx list
```

Или вручную задать ключ:

```bash
gib set-key
# либо: export OPENROUTER_API_KEY=sk-or-v1-...
```

**Для разработки:**

```bash
git clone https://github.com/devdevgot/gib.git
cd gib
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

---

## Команды

```bash
gib "Добавь JWT авторизацию"      # свободная задача — полный пайплайн
gib review [файлы]                 # code review + анализ безопасности
gib fix [файлы] --error "..."      # исправить баги
gib refactor <файлы>               # рефакторинг по SOLID
gib explain <путь>                 # объяснить код
gib test [файлы]                   # сгенерировать тесты
gib docs [файлы]                   # сгенерировать документацию
gib commit [--auto]                # умный git commit (Conventional Commits)
gib doctor                         # полная диагностика проекта
gib watch [папка]                  # live AI-фидбэк при сохранении файлов
gib chat                           # интерактивный чат с контекстом проекта
gib set-key                        # обновить API ключ
```

Полный справочник с примерами — [`COMMANDS.md`](./COMMANDS.md).

---

## Архитектура

GIB построен на **LangGraph** — каждая команда запускает отдельный граф агентов.  
Агенты работают параллельно там, где это возможно, и последовательно там, где важен порядок.

### Workflows

| Команда | Workflow | Граф |
|---------|----------|------|
| `gib "..."` | FEATURE | `analyzer → planner → [architect ‖ developer ‖ researcher] → merge → reviewer → security → tests → patch → git` |
| `gib fix` | BUGFIX | `analyzer → context → developer → reviewer → security → patch → git` |
| `gib review` | REVIEW | `analyzer → context → reviewer → security` |
| `gib refactor` | REFACTOR | `analyzer → context → architect → developer → reviewer → security → patch → git` |
| `gib explain` | EXPLAIN | `analyzer → context → explainer` |
| `gib doctor` | DOCTOR | `analyzer → context → [reviewer ‖ security ‖ researcher] → merge` |

`‖` — параллельное выполнение через `Send` из LangGraph.

### Структура модулей

```
gib/
├── cli/            # Typer CLI — все команды
├── orchestrator/   # Единая точка входа, делегирует в WorkflowRegistry
├── core/
│   ├── state.py    # GibState — единый TypedDict с reducers
│   ├── types.py    # WorkflowType, AgentRole, ReviewVerdict, ...
│   └── container.py # DI-контейнер зависимостей
├── nodes/          # LangGraph ноды (один файл = одна нода)
│   ├── analyzer.py        # анализ проекта
│   ├── context_builder.py # сборка контекста файлов
│   ├── task_planner.py    # декомпозиция задачи
│   ├── architect.py       # архитектурные решения
│   ├── developer.py       # генерация кода
│   ├── researcher.py      # исследование и best practices
│   ├── reviewer.py        # code review с авто-retry
│   ├── security.py        # статический анализ безопасности
│   ├── supervisor.py      # контроль качества
│   ├── test_generator.py  # генерация тестов
│   ├── patch_builder.py   # формирование патча
│   ├── approval.py        # human-in-the-loop подтверждение
│   ├── merge.py           # слияние параллельных результатов
│   └── git_node.py        # применение изменений
├── workflows/      # Сборка графов из нод
│   ├── base.py     # BaseWorkflow (абстрактный)
│   ├── feature.py  # Feature workflow
│   ├── bugfix.py   # BugFix workflow
│   ├── review.py   # Review workflow
│   ├── refactor.py # Refactor workflow
│   ├── explain.py  # Explain workflow
│   └── doctor.py   # Doctor workflow
├── graph/
│   └── registry.py # WorkflowRegistry — реестр и запуск workflow
├── agents/         # Legacy агенты (ProjectAnalyzer, Git, ...)
├── providers/      # OpenRouter API клиент
├── router/         # Умный выбор модели по типу задачи
├── memory/         # SQLite долговременная память
├── prompts/        # Шаблоны промптов
├── workspace/      # Профиль проекта
└── git/            # Git интеграция
```

### GibState

Единое состояние, которое прокидывается через все ноды графа:

```python
class GibState(TypedDict):
    user_request: str
    workflow_type: str
    target_paths: list[str]
    project_profile: dict
    file_contexts: Annotated[list, _append]
    subtasks: list[SubTask]
    agent_outputs: Annotated[list[AgentOutput], _append]
    code_result: str
    review_result: str
    research_result: str
    security_issues: Annotated[list[SecurityIssue], _append]
    patch_files: list[PatchFile]
    final_output: str
    models_used: Annotated[list[str], _append]
    total_cost_usd: Annotated[float, _sum_float]
    success: bool
```

### WorkflowRegistry (низкоуровневый API)

```python
from gib.graph.registry import WorkflowRegistry
from gib.core.state import make_initial_state
from gib.core.types import WorkflowType

state = make_initial_state(
    user_request="Исправить утечку памяти",
    workflow_type=WorkflowType.BUGFIX.value,
    target_paths=["app/worker.py"],
    error_input="MemoryError: unable to allocate array",
)

result = await WorkflowRegistry.run(WorkflowType.BUGFIX, state)
print(result["final_output"])
```

### Python API

```python
from gib.orchestrator import Orchestrator

orch = Orchestrator(root=Path("/my/project"))

result = await orch.run_general("Добавь rate limiting")
result = await orch.run_fix(paths=[Path("app/auth.py")], error="KeyError")
result = await orch.run_review([Path("app/")])
result = await orch.run_refactor([Path("app/services/")])
result = await orch.run_explain(Path("app/core/pipeline.py"))
result = await orch.run_doctor()
result = await orch.run_commit()

print(result.primary_output)
print(result.cost_str())     # "$0.0023"
```

---

## Конфигурация

`config.yaml` в корне проекта или `~/.gib/config.yaml`:

```yaml
models:
  default: "anthropic/claude-sonnet-4.5"
  fast: "google/gemini-2.5-flash"
  cheap: "deepseek/deepseek-v3.2"

routing:
  rules:
    - task_type: "review"
      model: "anthropic/claude-sonnet-4.5"
    - task_type: "docs"
      model: "google/gemini-2.5-flash"
    - task_type: "test"
      model: "deepseek/deepseek-v3.2"
```

Поддерживается любая модель из OpenRouter: Claude, GPT, Gemini, DeepSeek, Llama, Mistral, Qwen.

---

## Стек

| Компонент | Библиотека |
|-----------|-----------|
| Граф агентов | `langgraph >= 1.2.6` |
| LLM API | `httpx` + OpenRouter |
| CLI | `typer` + `rich` |
| Персистентность | `SQLAlchemy` + SQLite |
| Async | `asyncio` + `aiofiles` |
| Конфиг | `pydantic` + `python-dotenv` |
| Git | `GitPython` |
| Файловый watcher | `watchdog` |

## Требования

- Python 3.12+
- OpenRouter API ключ → [openrouter.ai/keys](https://openrouter.ai/keys)

## Лицензия

MIT
