---
name: okx-grid-bot
description: Use this skill for bug fixes, feature work, and safety reviews in the OKX grid bot codebase. Focus on trading safety, paper trading, risk controls, orchestrator workflows, and targeted test validation.
---

# OKX Grid Bot skill

## Scope
Use this skill when working in the OKX grid bot repository to:
- fix or extend the automated grid trading logic;
- review or improve preflight / exchange safety checks;
- debug paper trading or demo execution flows;
- update orchestrator, engine, or monitoring code;
- add or run focused validation tests without widening scope.

## Repository contract
This repo is governed by the workflow and safety rules in [AGENTS.md](../../AGENTS.md) and [AGENT_PROTOCOL.md](../../AGENT_PROTOCOL.md).

Follow these rules before making changes:
1. Work in an isolated branch/worktree.
2. Treat the task brief as the single source of truth.
3. Do one focused implementation pass per task.
4. Add/update targeted tests for the changed behavior.
5. Perform a self-review and confirm the patch matches the requirements.
6. Do not broaden scope beyond the blocker.

## Safety boundaries
This project handles live trading workflows and OKX exchange access. Follow these constraints strictly:
- Never place live exchange orders unless a preflight result is explicitly AUTHORIZED.
- Do not access or mutate live exchange state during ordinary development work.
- Prefer paper trading, demo flows, and deterministic tests for validation.
- Treat risk validation and preflight checks as first-class requirements, not afterthoughts.

## Primary areas of the codebase
- Application and entry points: [app.py](../../app.py), [main.py](../../main.py), [demo_trading.py](../../demo_trading.py), [paper_trading.py](../../paper_trading.py)
- Trading logic: [strategy/](../../strategy), [engine/](../../engine), [risk/](../../risk)
- Safety / validation layer: [preflight_layer/](../../preflight_layer)
- Orchestration: [orchestrator/](../../orchestrator)
- Tests: [tests/](../../tests)

## Working approach
1. Read the task brief and the exact files involved in the bug or feature.
2. Reproduce the issue with a small, relevant test or minimal repro.
3. Make the smallest root-cause fix that matches the spec.
4. Validate with the most focused test command available.
5. Review the diff for accidental scope creep or unsafe behavior.

## Preferred validation pattern
Use targeted tests first, for example:
- `pytest tests/test_grid_engine.py`
- `pytest tests/test_order_reconciler.py`
- `pytest tests/test_execution_safety.py`
- `pytest tests/test_paper_trading.py`

If the problem sits in orchestration or safety, prefer the nearest specific test module over a broad suite.

## Good default habits
- Keep changes minimal and explicit.
- Preserve paper-trading and demo behavior as the safe default path.
- If a risk or preflight rule is involved, verify the logic is enforced in code and covered by tests.
- Keep logs and state transitions understandable and traceable.
- Document assumptions when behavior is intentionally conservative.

## Red flags
Do not:
- add live-order execution paths during a normal fix;
- bypass preflight checks or risk gates;
- broaden a single bug fix into unrelated refactors;
- claim a fix is complete without fresh validation evidence.

## Output expectations
When you finish work on this repo, include:
- the concrete change made;
- which files were affected;
- the focused validation command(s) run;
- the outcome and any residual risk.

This skill is intended to keep work disciplined, safe, and aligned with the repository's trading and review standards.
