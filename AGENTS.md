# OKX Grid Bot Agent Guide

This repository is a trading and automation codebase with strict safety expectations. Treat the task brief as the source of truth, keep patches narrow, and prefer safe, deterministic validation paths.

## Required workflow

1. Work in an isolated branch or worktree.
2. Read the task brief and the exact files involved before editing.
3. Use one focused implementation pass per independent task.
4. Add or update a targeted test for the changed behavior.
5. Perform a self-review and confirm the fix matches the requirement.
6. Escalate only critical problems into a small, scoped rework loop.
7. Avoid broad refactors or unrelated cleanup.
8. Record decisions, evidence, and remaining risk when relevant.
9. Do not merge or push shared-branch changes without explicit human approval.
10. For repository reviews, use [.github/REVIEW_TEMPLATE.md](.github/REVIEW_TEMPLATE.md) and leave every applicable safety check with evidence.

## Project map

Primary entry points:

- [app.py](app.py) — loopback-only local dashboard for paper and demo trading workflows.
- [main.py](main.py) — core live trading loop and market/risk orchestration.
- [paper_trading.py](paper_trading.py) — paper-trading execution and state management.
- [demo_trading.py](demo_trading.py) — OKX demo account order flow with confirmation guards.

Core implementation areas:

- [strategy/](strategy) — grid and signal logic.
- [engine/](engine) — exchange and execution primitives.
- [risk/](risk) — risk management logic and limits.
- [preflight_layer/](preflight_layer) — validation, order manager, and safety gates.
- [orchestrator/](orchestrator) — runtime orchestration and agent-style task handling.
- [tests/](tests) and [orchestrator/tests/](orchestrator/tests) — pytest coverage for trading, safety, and orchestration behavior.

## Safety boundaries

This project handles live trading workflows and OKX exchange access. Follow these constraints strictly:

- Never place live exchange orders unless a preflight result is explicitly AUTHORIZED.
- Do not access or mutate live exchange state during routine development work.
- Prefer paper trading, demo flows, and deterministic unit tests for validation.
- Treat risk validation and preflight checks as first-class requirements, not as afterthoughts.
- Keep secrets and demo credentials out of code, logs, and test output.
- Do not broaden a single blocker into unrelated refactors or feature work.

For OKX trading work, a preflight result other than AUTHORIZED is never permission to place an exchange order.

## Validation habits

Use the narrowest relevant command first. Prefer targeted tests over full-suite runs when debugging a change.

Common project checks:

- `python -m pytest -q tests/test_paper_trading.py tests/test_demo_trading.py`
- `pytest tests/test_grid_engine.py`
- `pytest tests/test_order_reconciler.py`
- `pytest tests/test_execution_safety.py`
- `pytest -q` when the broader project baseline is required

CI in [.github/workflows/ci.yml](.github/workflows/ci.yml) also runs a Python compile check and the full pytest suite in a clean environment.

## Coding conventions

- Keep changes minimal, explicit, and scoped to the issue at hand.
- Read the exact files implicated by the bug or feature before patching.
- Add or update targeted regression tests alongside the fix.
- Preserve the safer default paths: paper trading and demo flows before live execution.
- If risk or preflight rules are involved, assert the guardrail in both code and tests.
- Keep logs, state transitions, and exceptions understandable and traceable.
- Document assumptions when the repo intentionally chooses conservative behavior.

## References

- [README.md](README.md)
- [AGENT_PROTOCOL.md](AGENT_PROTOCOL.md)
- [.github/REVIEW_TEMPLATE.md](.github/REVIEW_TEMPLATE.md)
- [.github/skills/okx-grid-bot/SKILL.md](.github/skills/okx-grid-bot/SKILL.md)
- [.github/skills/okx-trading-safety/SKILL.md](.github/skills/okx-trading-safety/SKILL.md)
- [.github/workflows/ci.yml](.github/workflows/ci.yml)

## Human gate

The agent may prepare and report a change as ready for review. It may not merge without separate explicit human approval.
