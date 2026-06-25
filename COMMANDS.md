# GIB — Команды оркестратора

## Установка

```bash
pip install -e .
```

Первый запуск попросит API ключ OpenRouter. Или вручную:

```bash
gib set-key
```

---

## Свободная задача

```bash
gib "Добавь JWT аутентификацию к FastAPI"
gib "Перепиши UserService с использованием паттерна Repository"
gib "Создай CRUD для модели Product"
```

**Workflow**: `analyzer → context_builder → task_planner → [architect ‖ developer ‖ researcher] → merge → reviewer → security → test_generator → patch_builder → approval → git`

---

## Команды

### `gib review [файлы...]`

Code review с безопасностью и архитектурными замечаниями.

```bash
gib review                          # весь проект
gib review gib/orchestrator/core.py
gib review gib/nodes/ gib/workflows/
```

**Workflow**: `analyzer → context_builder → reviewer → security`

---

### `gib fix [файлы...] [--error "..."]`

Исправление багов. Принимает файлы и/или текст ошибки.

```bash
gib fix                                         # весь проект
gib fix gib/nodes/developer.py
gib fix --error "AttributeError: 'NoneType' object has no attribute 'run'"
gib fix gib/pipeline/ --error "$(cat error.log)"
```

**Workflow**: `analyzer → context_builder → developer → reviewer → security → patch_builder → approval → git`

---

### `gib refactor <файлы...>`

Рефакторинг по SOLID, clean code, устранение code smells.

```bash
gib refactor gib/orchestrator/core.py
gib refactor gib/nodes/ gib/workflows/
```

**Workflow**: `analyzer → context_builder → architect → developer → reviewer → security → patch_builder → approval → git`

---

### `gib explain <путь>`

Детальное объяснение кода: что делает, как устроено, зачем.

```bash
gib explain gib/graph/registry.py
gib explain gib/workflows/
```

**Workflow**: `analyzer → context_builder → explainer`

---

### `gib test [файлы...]`

Генерация тестов: unit, integration, edge cases.

```bash
gib test                              # весь проект
gib test gib/nodes/developer.py
gib test gib/workflows/feature.py
```

---

### `gib docs [файлы...]`

Генерация документации: docstrings, README, API docs.

```bash
gib docs                              # весь проект
gib docs gib/orchestrator/
gib docs gib/core/state.py
```

---

### `gib commit [--auto]`

Генерирует Conventional Commits сообщение по diff, предлагает закоммитить.

```bash
gib commit             # генерирует + спрашивает подтверждение
gib commit --auto      # генерирует + коммитит без вопросов
```

---

### `gib doctor`

Полная диагностика проекта: баги, мёртвый код, безопасность, архитектура.

```bash
gib doctor
```

**Workflow**: `analyzer → context_builder → [reviewer ‖ security ‖ researcher] → doctor_merge`

---

### `gib watch [папка]`

Следит за файлами, даёт AI-фидбэк при каждом сохранении.

```bash
gib watch              # текущая директория
gib watch gib/nodes/
```

---

### `gib chat`

Интерактивный чат с контекстом проекта.

```bash
gib chat
```

---

## Прямой вызов оркестратора (Python API)

```python
import asyncio
from pathlib import Path
from gib.orchestrator import Orchestrator

orch = Orchestrator(root=Path("/my/project"))

# Свободная задача
result = asyncio.run(orch.run_general("Добавь rate limiting"))

# Fix с ошибкой
result = asyncio.run(orch.run_fix(
    paths=[Path("app/auth.py")],
    error="KeyError: 'user_id'"
))

# Review
result = asyncio.run(orch.run_review([Path("app/")]))

# Refactor
result = asyncio.run(orch.run_refactor([Path("app/services/")]))

# Explain
result = asyncio.run(orch.run_explain(Path("app/core/pipeline.py")))

# Doctor
result = asyncio.run(orch.run_doctor())

# Commit message
result = asyncio.run(orch.run_commit())

# Tests
result = asyncio.run(orch.run_test([Path("app/auth.py")]))

# Docs
result = asyncio.run(orch.run_docs([Path("app/")]))

print(result.primary_output)
print(f"Cost: {result.cost_str()}")
print(f"Models: {result.model_used}")
```

---

## WorkflowRegistry (низкоуровневый API)

```python
import asyncio
from gib.graph.registry import WorkflowRegistry
from gib.core.state import make_initial_state
from gib.core.types import WorkflowType

state = make_initial_state(
    user_request="Исправить утечку памяти",
    workflow_type=WorkflowType.BUGFIX.value,
    target_paths=["app/worker.py"],
    error_input="MemoryError: unable to allocate array",
)

result = asyncio.run(WorkflowRegistry.run(WorkflowType.BUGFIX, state))

print(result["final_output"])
print(result["models_used"])
print(result["total_cost_usd"])
```

---

## OrchestratorResult — поля

| Поле | Тип | Описание |
|------|-----|----------|
| `success` | `bool` | Успешно ли завершился workflow |
| `primary_output` | `str` | Главный вывод (код, ревью, объяснение) |
| `pipeline_steps` | `list[PipelineStep]` | Шаги пайплайна с моделями и стоимостью |
| `total_cost_usd` | `float` | Суммарная стоимость в USD |
| `total_latency_ms` | `int` | Время выполнения в мс |
| `model_used` | `str` | Последняя использованная модель |
| `cost_str()` | `str` | Форматированная стоимость (`$0.0023`) |

---

## Workflows и их граф

| Команда | Workflow | Параллелизм |
|---------|----------|-------------|
| `gib "..."` | FEATURE | architect ‖ developer ‖ researcher |
| `gib fix` | BUGFIX | — |
| `gib review` | REVIEW | — |
| `gib refactor` | REFACTOR | — |
| `gib explain` | EXPLAIN | — |
| `gib doctor` | DOCTOR | reviewer ‖ security ‖ researcher |
| `gib test` | FEATURE | architect ‖ developer ‖ researcher |
| `gib docs` | FEATURE | architect ‖ developer ‖ researcher |
