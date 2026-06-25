# GIB — AI Development Operating System

> Терминальный AI-оркестратор для разработки. Аналог Cursor Agent и Claude Code с поддержкой любых моделей через OpenRouter.

## Быстрый старт

### 1. Установка

```bash
git clone <repo>
cd gib
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. API ключ

```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key-here
# Или добавь в .env файл в директории проекта
```

### 3. Запуск

```bash
gib                              # Показать помощь
gib "Добавь JWT авторизацию"     # Свободный запрос
gib review                       # Code review
gib fix                          # Исправить баги
gib refactor src/                # Рефакторинг
gib commit                       # Умный git commit
gib doctor                       # Диагностика проекта
gib explain app/auth.py          # Объяснить файл
gib test                         # Сгенерировать тесты
gib docs                         # Сгенерировать документацию
gib watch                        # Live наблюдение за файлами
gib chat                         # Интерактивный чат
```

## Команды

| Команда | Описание | Пример |
|---------|----------|--------|
| `gib "prompt"` | Свободный запрос | `gib "Добавь авторизацию"` |
| `gib review` | Code review | `gib review src/` |
| `gib fix` | Исправление багов | `gib fix main.py --error "TypeError"` |
| `gib refactor` | Рефакторинг | `gib refactor src/` |
| `gib commit` | Git commit | `gib commit --auto` |
| `gib doctor` | Диагностика | `gib doctor` |
| `gib explain` | Объяснение кода | `gib explain auth.py` |
| `gib test` | Генерация тестов | `gib test services/` |
| `gib docs` | Документация | `gib docs api/` |
| `gib watch` | Live наблюдение | `gib watch src/` |
| `gib chat` | Интерактивный чат | `gib chat` |

## Конфигурация

Редактируй `config.yaml`:

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

Любая модель с OpenRouter: Claude, GPT, Gemini, DeepSeek, Llama, Mistral, Qwen.

## Архитектура

```
gib/
├── cli/           # Typer CLI — все команды
├── orchestrator/  # Координирует агентов
├── agents/        # 9 независимых агентов
│   ├── project_analyzer.py
│   ├── architect.py
│   ├── developer.py
│   ├── reviewer.py
│   ├── tester.py
│   ├── documenter.py
│   ├── git_agent.py
│   └── memory_agent.py
├── providers/     # OpenRouter API клиент
├── router/        # Интеллектуальный выбор модели
├── memory/        # SQLite долговременная память
├── prompts/       # Шаблоны промптов
├── workspace/     # Анализ проекта
├── git/           # Git интеграция
└── terminal/      # Выполнение команд
```

## Переменные окружения

| Переменная | Описание |
|-----------|----------|
| `OPENROUTER_API_KEY` | API ключ OpenRouter (обязательно) |

## Требования

- Python 3.12+
- OpenRouter API ключ

## Лицензия

MIT
