# GIB

**AI-оркестратор для разработки в терминале** — аналог Cursor Agent и Claude Code.

GIB анализирует ваш проект, строит граф агентов на LangGraph и выполняет задачи через OpenRouter: архитектура, код, ревью, тесты, безопасность и git — с подтверждением перед применением изменений.

> Все ответы, отчёты и сообщения CLI — **на русском языке**.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-orange.svg)](https://openrouter.ai/)
[![Version](https://img.shields.io/badge/version-0.1.7-green.svg)](https://github.com/devdevgot/gib)

---

## Возможности

| Возможность | Описание |
|-------------|----------|
| **Мульти-агентный пайплайн** | Архитектор, разработчик, исследователь и ревьюер работают параллельно где возможно |
| **Полный контекст проекта** | Сканирование репозитория, память между сессиями, семантический поиск файлов |
| **Любые модели** | Claude, GPT, Gemini, DeepSeek и другие через [OpenRouter](https://openrouter.ai/models) |
| **Checkpoint + resume** | При нехватке кредитов прогресс сохраняется — продолжение через `gib resume` |
| **Human-in-the-loop** | Diff и подтверждение перед записью в git |
| **Статический security scan** | SQL injection, XSS, секреты, JWT, weak crypto — без LLM |

---

## Быстрый старт

```bash
pipx install git+https://github.com/devdevgot/gib.git
gib улучши страницу дашборда          # свободная задача — без кавычек
gib -y добавь кнопку экспорта в таблицу  # применить без подтверждения
```

Получить ключ: [openrouter.ai/keys](https://openrouter.ai/keys)

### Обновление

```bash
pip uninstall gib -y 2>/dev/null || true
pipx install --force git+https://github.com/devdevgot/gib.git@main
hash -r
gib --version   # 0.1.7
```

### Разработка из исходников

```bash
git clone https://github.com/devdevgot/gib.git
cd gib
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

---

## Команды

```bash
gib улучши страницу дашборда       # свободная задача — без кавычек
gib -y добавь валидацию email      # применить изменения сразу
gib review [файлы]                  # код-ревью + security scan
gib fix [файлы] --error "..."       # исправить баги
gib refactor <файлы>                # рефакторинг по SOLID
gib explain <путь>                  # объяснить код
gib test [файлы]                    # сгенерировать тесты
gib docs [файлы]                    # сгенерировать документацию
gib commit [--auto]                 # умный git commit (Conventional Commits)
gib doctor                          # полная диагностика проекта
gib watch [папка]                   # live AI-фидбэк при сохранении файлов
gib chat                            # интерактивный чат с контекстом проекта
gib resume [--list] [--id <uuid>]   # продолжить после нехватки кредитов
gib set-key                         # обновить API-ключ
```

Подробные примеры — в [`COMMANDS.md`](./COMMANDS.md).

---

## Модели по умолчанию

Трёхмодельная архитектура GIB (настраивается в `config.yaml`):

| Роль | Модель OpenRouter | Задачи |
|------|-------------------|--------|
| **Архитектор** | `anthropic/claude-opus-4.8` | Планирование, архитектура, рефакторинг, объяснения, чат |
| **Разработчик** | [`z-ai/glm-5.2`](https://openrouter.ai/z-ai/glm-5.2) | Код, багфиксы, тесты, коммиты, watch |
| **Исследователь** | `google/gemini-2.5-pro` | Best practices, документация, совместимость |
| **Ревьюер** | `google/gemini-2.5-pro` | Код-ревью, doctor, длинный контекст |
| **Вспомогательные** | `gemini-2.5-flash` / `deepseek-v3.2` | file finder, дешёвые вспомогательные вызовы |

Любую модель можно заменить в `~/.gib/config.yaml` — см. [каталог OpenRouter](https://openrouter.ai/models).

> **Важно:** при обновлении удалите старый `~/.gib/config.yaml` или синхронизируйте модели вручную — файл копируется при первом запуске и не перезаписывается автоматически.

### Пример конфигурации

```yaml
# ~/.gib/config.yaml

models:
  default: "anthropic/claude-opus-4.8"   # архитектор
  code: "z-ai/glm-5.2"                    # разработчик
  reviewer: "google/gemini-2.5-pro"       # ревьюер
  fast: "google/gemini-2.5-flash"
  cheap: "deepseek/deepseek-v3.2"

routing:
  rules:
    - task_type: "architecture"
      model: "anthropic/claude-opus-4.8"
    - task_type: "development"
      model: "z-ai/glm-5.2"
    - task_type: "research"
      model: "google/gemini-2.5-pro"
    - task_type: "review"
      model: "google/gemini-2.5-pro"
```

API-ключ хранится в `~/.gib/.env` (`OPENROUTER_API_KEY=sk-or-...`).

---

## Возобновление после нехватки кредитов

При ошибке баланса OpenRouter GIB сохраняет checkpoint в `<проект>/.gib/checkpoints.db` и метаданные задачи в `<проект>/.gib/memory.db`.

```bash
gib resume              # продолжить последнюю приостановленную задачу
gib resume --list       # список приостановленных задач
gib resume --id <uuid>  # продолжить конкретную задачу
```

---

## Архитектура

Каждая команда запускает отдельный **LangGraph workflow**. Агенты работают параллельно (`Send`) там, где нет зависимостей, и последовательно — где важен порядок.

### Workflows

| Команда | Workflow | Граф |
|---------|----------|------|
| `gib "..."` | FEATURE | `analyzer → context → file_finder → planner → architect → [developer ‖ researcher] → merge → reviewer → security → tests → patch → approval → git` |
| `gib fix` | BUGFIX | `analyzer → context → file_finder → developer → reviewer → security → patch → approval → git` |
| `gib review` | REVIEW | `analyzer → context → reviewer → security` |
| `gib refactor` | REFACTOR | `analyzer → context → file_finder → architect → developer → reviewer → security → patch → approval → git` |
| `gib explain` | EXPLAIN | `analyzer → context → explainer` |
| `gib doctor` | DOCTOR | `analyzer → context → [reviewer ‖ security ‖ researcher] → merge` |
| `gib test` / `gib docs` | FEATURE | тот же пайплайн, что и свободная задача |

`‖` — параллельное выполнение. Ревьюер может вернуть задачу разработчику (до 2 итераций).

### Пайплайн свободной задачи

```
Запрос пользователя
       │
       ▼
  Анализ проекта ──► Контекст файлов ──► Поиск файлов ──► Планировщик
       │
       ▼
   Архитектор (Claude Opus 4.8)
       │
       ├──────────────────┐
       ▼                  ▼
  Разработчик (GLM 5.2)   Исследователь (Gemini 2.5 Pro)   ← параллельно
       │                  │
       └────────┬─────────┘
                ▼
            Merge ──► Ревьюер (Gemini 2.5 Pro) ──► Security ──► Тесты ──► Патч
                                                              │
                                                              ▼
                                                    Подтверждение ──► Git
```

### Структура проекта

```
gib/
├── cli/              # Typer CLI — все команды
├── orchestrator/     # Единая точка входа
├── workflows/        # Сборка LangGraph-графов
├── nodes/            # Узлы графа (один файл = одна нода)
├── graph/registry.py # Реестр workflow
├── core/             # GibState, типы, DI-контейнер
├── providers/        # OpenRouter API
├── router/           # Маршрутизация моделей по типу задачи
├── memory/           # SQLite: задачи, чат, checkpoint resume
├── prompts/          # Шаблоны промптов
├── workspace/        # Анализ профиля проекта
└── git/              # Git интеграция
```

### Память

| Файл | Назначение |
|------|------------|
| `<проект>/.gib/memory.db` | История задач, чат-сессии, профили проекта, paused runs |
| `<проект>/.gib/checkpoints.db` | LangGraph checkpoints для `gib resume` |
| `<проект>/.gib/logs/` | Логи сессий |
| `~/.gib/config.yaml` | Модели и маршрутизация (глобально) |
| `~/.gib/.env` | `OPENROUTER_API_KEY` (глобально) |

Каждый проект хранит память и checkpoints локально в `.gib/` — переключение между проектами не вызывает конфликтов SQLite. При первом запуске `gib` автоматически добавляет `.gib/` в `.gitignore` проекта и удаляет устаревшие глобальные `~/.gib/memory.db` и `~/.gib/checkpoints.db`.

Контекст предыдущих задач и чата подмешивается в новые workflow автоматически.

---

## Python API

```python
import asyncio
from pathlib import Path
from gib.orchestrator import Orchestrator

orch = Orchestrator(root=Path("/my/project"))

result = asyncio.run(orch.run_general("Добавь rate limiting"))
result = asyncio.run(orch.run_fix(paths=[Path("app/auth.py")], error="KeyError"))
result = asyncio.run(orch.run_review([Path("app/")]))
result = asyncio.run(orch.run_resume())          # после нехватки кредитов

print(result.primary_output)
print(result.cost_str())       # "$0.0023"
print(result.model_used)
```

Низкоуровневый доступ через `WorkflowRegistry` — см. [`COMMANDS.md`](./COMMANDS.md).

---

## Стек

| Компонент | Библиотека |
|-----------|-----------|
| Граф агентов | LangGraph + langgraph-checkpoint-sqlite |
| LLM API | httpx → OpenRouter |
| CLI | Typer + Rich |
| Память | SQLAlchemy + SQLite |
| Git | GitPython |
| Watcher | watchdog |

## Требования

- Python **3.12+**
- API-ключ [OpenRouter](https://openrouter.ai/keys)
- Опционально: `ripgrep` (`rg`) — ускоряет поиск файлов в `file_finder`

## Лицензия

MIT
