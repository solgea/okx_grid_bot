# Superpowers Subagent Workflow

This document turns the Superpowers subagent-driven-development method into a repository-level operating contract.

## Workspace

Every implementation sequence gets its own isolated workspace and ledger under:

`.superpowers/sdd/<plan-identity>/`

The ledger starts with:

`# SDD ledger — plan: <plan file path>`

Never reuse another plan's ledger.

## Plan authority

- The specification is the binding authority.
- The implementation plan operationalizes the specification.
- Conflicts are recorded as rulings.
- If neither answers an ambiguity, choose the smallest defensible path and record why and the cost if wrong.

## Implementer

Each independent task gets a fresh implementer.

The implementer receives the task brief, required interfaces/decisions, global safety constraints, and report path.

The implementer does not spawn subagents, implements only the assigned task, runs covering tests, self-reviews, and writes its report.

## Task review

Every completed task receives an independent review.

The reviewer receives the same brief, implementer report, review package, and binding constraints.

The reviewer returns separate verdicts for specification compliance and task quality.

A task is complete only when both pass, or when the five-round breaker is reached and remaining findings are explicitly adjudicated and recorded.

## Fix/re-review loop

For Critical or Important findings:

- rounds 1–3: resume the original implementer where supported;
- rounds 4–5: use a fresh, more capable implementer;
- every round includes tests and a scoped re-review;
- maximum 5 rounds per task.

Never silently dismiss findings.

## Final review

After all tasks:

1. Generate one whole-branch review package from merge-base to HEAD.
2. Use the most capable available reviewer.
3. If findings remain, dispatch one consolidated fix pass.
4. Perform exactly one scoped re-review of that fix pass.
5. Adjudicate residual findings using the same evidence/ruling rules.

## Git and CI

Agents may create branches and commits within their authorized workspace and may observe/request CI when authorized.

Shared-branch operations are human-controlled:

- merge requires explicit human approval;
- production deployment requires explicit human approval;
- live exchange actions are prohibited.

## Audit ledger

Record at minimum:

- task ID and state;
- agent role/identity;
- action and policy decision;
- test command/result;
- commit SHA;
- CI run/status;
- review verdict;
- final outcome;
- remaining risk.

## Definition of done

DONE means implementation is complete and independently reviewed with evidence.

It does not mean merged, deployed, live-trading enabled, or gate frozen solely because CI passed.
