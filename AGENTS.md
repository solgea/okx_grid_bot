# Repository Agent Contract

This repository uses a persistent Superpowers-inspired subagent workflow for engineering work.

## Required workflow

1. Work in an isolated branch/worktree.
2. Read the task brief as the single source of task requirements.
3. Use one fresh implementer per independent task.
4. Require implementer tests and self-review.
5. Perform an independent task review for specification compliance and code quality.
6. Critical/Important findings enter a scoped fix/re-review loop, maximum 5 rounds.
7. Perform one whole-branch review after all tasks.
8. Final-review findings receive one consolidated fix pass and one scoped re-review.
9. Record decisions, findings, tests, commits, CI, and outcomes in the task ledger.
10. Human approval is required before merge or other shared-branch side effects.

## Safety boundaries

Agents may read, analyze, plan, modify code/docs/tests, run tests, create commits, request/observe CI, and report evidence when explicitly authorized.

Agents must not autonomously:

- place live exchange orders;
- access or mutate live exchange state;
- deploy production;
- merge pull requests;
- change policy or safety controls;
- broaden a single-blocker task into a batch fix.

For OKX trading work, a preflight result other than AUTHORIZED is never permission to place an exchange order.

## Evidence standard

Completion requires focused test evidence where applicable, self-review/report, independent review, commit SHA, CI evidence when required, and an explicit remaining-risk statement. Passing CI alone does not close a gate.

## Human gate

The agent may prepare and report a change as ready for review. It may not merge without separate explicit human approval.
