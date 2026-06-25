# GIB Pipeline Rebuild Task

## Status: IN PROGRESS

## Done ✅
- core/types.py — TaskType, WorkflowType, AgentRole, ApprovalStatus, SubTask, PatchFile, AgentOutput, SecurityIssue
- core/state.py — GibState (TypedDict + Annotated reducers), make_initial_state()
- core/container.py — DI Container singleton
- core/__init__.py
- nodes/__init__.py
- nodes/analyzer.py — ProjectAnalyzer (no LLM)
- nodes/context_builder.py — ContextBuilder (no LLM)
- nodes/task_planner.py — TaskPlanner (Claude)
- nodes/supervisor.py — Supervisor (pure Python)
- nodes/architect.py — Architect (Claude)
- nodes/developer.py — Developer (GPT)
- nodes/researcher.py — Researcher (Gemini)
- nodes/merge.py — Merge node (Claude)
- nodes/reviewer.py — Reviewer (Claude) + route_after_review
- nodes/security.py — Security Scanner (static analysis, no LLM)
- nodes/test_generator.py — Test Generator (auto-detect framework)
- nodes/patch_builder.py — Patch Builder (diff, no file writes)
- nodes/approval.py — Human Approval (Rich UI)
- nodes/git_node.py — Git Agent
- workflows/base.py — BaseWorkflow (ABC)
- workflows/feature.py — FeatureWorkflow (full parallel pipeline)
- workflows/bugfix.py — BugFixWorkflow
- workflows/review.py — ReviewWorkflow
- workflows/refactor.py — RefactorWorkflow
- workflows/explain.py — ExplainWorkflow
- workflows/doctor.py — DoctorWorkflow (parallel diagnosis)
- workflows/__init__.py
- graph/registry.py — WorkflowRegistry (extensible)
- graph/__init__.py
- router/model_router.py — updated with new TaskTypes

## TODO ⏳
1. Update orchestrator/core.py — use WorkflowRegistry
2. Update prompts/templates.py — add pipeline_architect, pipeline_developer, pipeline_reviewer prompts
3. Verify imports compile: `python -c "from gib.workflows import FeatureWorkflow; print('OK')"`
4. Update pyproject.toml if needed (already has langgraph/langchain-core)
5. git commit + push
6. Test run

## Known Issues
- PromptLibrary in task_planner/nodes uses methods that might not exist yet
- Need to verify all imports resolve correctly
