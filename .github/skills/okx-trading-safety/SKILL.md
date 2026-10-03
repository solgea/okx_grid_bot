---
name: okx-trading-safety
description: Use this skill to review, add, or validate security and risk controls in the OKX grid bot repository. Focus on preflight gates, demo/paper safety defaults, authorization enforcement, and guarded live-execution paths.
---

# OKX Trading Safety Skill

## Scope
Use this skill when working on:
- preflight validation and order authorizations;
- risk gates, kill switches, and exposure limits;
- demo or paper-trading approval logic;
- code paths that could reach OKX execution or live state mutation;
- security reviews for new order, balance, or market-data flows.

This repo is governed by [AGENTS.md](../../AGENTS.md), [AGENT_PROTOCOL.md](../../AGENT_PROTOCOL.md), and the safety expectations in [README.md](../../README.md).

## Security principles
1. Fail closed: if a required check cannot be verified, block the action.
2. Never assume a live order is allowed just because the code path exists.
3. Prefer paper and demo workflows as the safe default path during development.
4. Treat risk validation and authorization as part of the business logic, not a late validation step.
5. Keep secrets and credentials out of logs, user-visible output, and test fixtures.

## Required checks before any live or privileged action
Before a code path can place an order, mutate exchange state, or start a live trading loop, confirm all of the following:
- A preflight result is explicitly `AUTHORIZED`.
- The symbol, leverage, and order arguments match the project configuration and validation contract.
- The account is not in a state that violates risk or exposure rules.
- Market data is fresh enough to support the action.
- The user or workflow has explicitly approved the operation when the code requires confirmation.
- The path is not accidentally executing through a demo or paper-only branch.

If any check fails, the result is denied and the code should return a clear, traceable error.

## Project-specific guardrails
This repository has explicit patterns that should be preserved:
- Paper trading and demo flows are safer default execution paths.
- OKX demo trading requires explicit demo credentials and `IS_DEMO` enforcement.
- Live order execution must never be allowed by a permissive default or a missing guard.
- Risk and preflight logic should be validated with deterministic tests, not only by manual inspection.

Key project areas to review when adding or changing controls:
- [preflight_layer/](../../preflight_layer)
- [risk/](../../risk)
- [engine/](../../engine)
- [strategy/](../../strategy)
- [app.py](../../app.py)
- [main.py](../../main.py)
- [paper_trading.py](../../paper_trading.py)
- [demo_trading.py](../../demo_trading.py)

## Review checklist for changes
Before approving a patch that touches trading safety:
- Does the change preserve the fail-closed rule?
- Is the validation logic explicit, not inferred from surrounding code?
- Are error messages clear and actionable without exposing secrets?
- Are the relevant tests updated or added?
- Does the patch avoid broad cleanup or unrelated refactors?
- Does the change maintain the separation between paper, demo, and live execution paths?

## Risk review checklist
Use this checklist for any review, patch, or incident response involving trading logic or execution flow:

### 1. Authorization gate
- Is there an explicit authorization state before any live action?
- Does the code require `AUTHORIZED` and reject unknown, missing, or stale states?
- Is there any path where a default or fallback could silently authorize execution?

### 2. Demo vs paper vs live separation
- Are demo, paper, and live flows clearly separated by branch or configuration?
- Can a paper-only path accidentally reach a live API call?
- Are tests covering the safe default path for non-live execution?

### 3. Exposure and risk controls
- Are order size, leverage, max drawdown, and exposure rules enforced in code?
- Are limits applied before placement, not after the fact?
- Is there a safe stop path if a risk check fails?

### 4. Market-data and state validity
- Is market data freshness validated before acting on it?
- Are stale or partial responses treated as invalid input?
- Are symbol, leverage, and order parameters checked against the expected contract?

### 5. Secrets and operational safety
- Are credentials, demo keys, and sensitive state excluded from logs and test output?
- Are exceptions and error messages sanitized to avoid leaking tokens or account context?
- Are operational actions reversible or blocked when the environment is not trusted?

### 6. Regression and evidence
- Has a targeted test been added or updated for the changed guardrail?
- Is the validation command narrow and relevant to the changed behavior?
- Does the final report include the exact validation result and any residual risk?

## Validation pattern
Prefer the smallest relevant test command first. Examples:
- `pytest tests/test_execution_safety.py`
- `pytest tests/test_paper_trading.py`
- `pytest tests/test_demo_trading.py`
- `pytest tests/test_grid_engine.py`
- `pytest -q` only when the change broadens the validation surface or the repository baseline is required.

When the change affects preflight or risk gating, verify both the guard and the regression test.

## Red flags
Do not:
- bypass or weaken preflight checks;
- allow live execution with missing authorization state;
- widen scope into unrelated refactors to “clean up” safety logic;
- rely on logs or environment state as a substitute for an explicit authorization result;
- suppress exceptions that should halt a risky action;
- merge a change without a focused validation result.

## Output expectations
When finishing work in this repository, report:
- what security or safety control changed;
- which files were touched;
- the validation command(s) run;
- the result and any remaining risk.

This skill is intended to keep trading flows conservative, auditable, and aligned with the repo’s actual risk model.
