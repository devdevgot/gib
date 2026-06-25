# GIB — Production LangGraph Pipeline Architecture

## Module Map
```
gib/
├── core/                    # Ядро: state, base types, DI container
│   ├── state.py             # Единый GibState (TypedDict + reducers)
│   ├── types.py             # Перечисления, dataclasses
│   └── container.py         # Dependency Injection container
├── providers/               # Слой доступа к моделям (только OpenRouter)
│   ├── openrouter.py        # Единственный провайдер
│   ├── models.py            # Реестр моделей + метаданные
│   └── base.py              # Абстракции
├── router/                  # Интеллектуальный роутер моделей
│   └── model_router.py      # Выбор модели по типу задачи
├── nodes/                   # Все LangGraph узлы (1 файл = 1 ответственность)
│   ├── analyzer.py          # ProjectAnalyzer (чистый Python, без LLM)
│   ├── context_builder.py   # ContextBuilder (чистый Python)
│   ├── task_planner.py      # TaskPlanner (Claude)
│   ├── supervisor.py        # Supervisor (управляет флоу)
│   ├── model_router_node.py # ModelRouter Node
│   ├── architect.py         # Architect Agent (Claude)
│   ├── developer.py         # Developer Agent (GPT)
│   ├── researcher.py        # Research Agent (Gemini)
│   ├── merge.py             # Merge результатов
│   ├── reviewer.py          # Code Reviewer (Claude)
│   ├── security.py          # Security Scanner (статика + LLM)
│   ├── test_generator.py    # Test Generator
│   ├── patch_builder.py     # Patch Builder (Git Diff)
│   ├── approval.py          # Human Approval (Rich UI)
│   └── git_node.py          # Git Integration
├── workflows/               # Независимые графы под каждый тип задачи
│   ├── base.py              # BaseWorkflow
│   ├── feature.py           # Feature Workflow
│   ├── bugfix.py            # BugFix Workflow
│   ├── review.py            # Review Workflow
│   ├── refactor.py          # Refactor Workflow
│   ├── explain.py           # Explain Workflow
│   └── doctor.py            # Doctor Workflow
├── memory/                  # SQLite долговременная память
│   └── store.py
├── graph/                   # Реестр графов + фабрики
│   └── registry.py
└── agents/                  # (legacy — используются workflows)
