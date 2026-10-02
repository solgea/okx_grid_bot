# Master Orchestrator Runtime & Task Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build a real, local, observable runtime entrypoint around the existing MasterOrchestrator so repository tasks can be submitted and delegated through Planner/Engineering/Test/Reviewer.

**Architecture:** Add a thin runtime layer around the existing state machine and ActionDispatcher. A validated intake feeds a local persistent store and RuntimeService; a CLI exposes submit/status/report. No new agent framework, exchange access, production deployment, GitHub automation, or G8-PF031 implementation.

**Tech Stack:** Existing Python codebase, standard-library runtime/persistence where practical, existing pytest suite, existing MasterOrchestrator/ActionDispatcher/policy/state contracts.

**Spec:** docs/superpowers/specs/2026-10-03-master-orchestrator-runtime-task-intake-design.md

## Global Constraints

- Do not duplicate the MasterOrchestrator state machine.
- Use the existing ActionDispatcher for Planner/Engineering/Test/Reviewer.
- Persistence is local, deterministic, test-isolatable, and has no external database dependency.
- Invalid/unsafe tasks fail closed.
- LIVE_ORDER, LIVE_EXCHANGE, LIVE_ACCOUNT_MUTATION, PRODUCTION_DEPLOY, POLICY_CHANGE, and MERGE_PR remain denied.
- PreFlight != AUTHORIZED is never permission to submit an exchange order.
- Runtime completion does not imply merge, deployment, live trading, or G8/G9 closure.
- G8-PF031 is explicitly out of scope.
- No broad exception swallowing.
- COMMITTED requires commit evidence; successful verification requires explicit Test Agent evidence.

## Review Focus

1. Crash/partial-write recovery: last durable state and audit history remain readable.
2. Unsafe capabilities: forbidden task actions cannot reach agent execution.
3. Duplicate task IDs: existing history cannot be silently overwritten.
4. CLI errors: malformed input/unknown IDs fail deterministically without mutation.
5. Terminal evidence: reviewer success alone cannot produce COMMITTED.

---

### Task 1: Runtime Contracts and Local Persistence

**Files**
- Create: orchestrator/runtime/__init__.py
- Create: orchestrator/runtime/models.py
- Create: orchestrator/runtime/intake.py
- Create: orchestrator/runtime/store.py
- Test: orchestrator/tests/test_runtime_intake_store.py

**Interfaces**
- TaskIntake.validate(payload) -> Task
- TaskStore.create(task) -> TaskRecord
- TaskStore.get(task_id) -> TaskRecord
- TaskStore.record_transition(task_id, state, evidence) -> TaskRecord
- TaskStore.report(task_id) -> dict

- [ ] Write failing tests for valid, invalid, unsafe, duplicate task IDs, ordered audit events, reopen persistence, and temp-directory isolation.
- [ ] Run: pytest orchestrator/tests/test_runtime_intake_store.py -v. Expected: import/contract failures.
- [ ] Implement the smallest typed models, fail-closed intake, and readable append-ordered local store. Duplicate IDs must be rejected, not overwritten.
- [ ] Run the focused tests again. Expected: PASS.
- [ ] Commit: feat: add orchestrator task intake and local store

### Task 2: Runtime Service Wiring

**Files**
- Create: orchestrator/runtime/service.py
- Test: orchestrator/tests/test_runtime_service.py

**Interfaces**
- RuntimeService.submit(payload) -> TaskRecord
- RuntimeService.run(task_id) -> TaskRecord
- RuntimeService.status(task_id) -> dict
- RuntimeService.report(task_id) -> dict

- [ ] Write failing integration tests using injected Planner/Engineering/Test/Reviewer dispatch doubles and a fake commit executor; assert ordered dispatch, persisted evidence, explicit verification, and commit SHA requirements.
- [ ] Run: pytest orchestrator/tests/test_runtime_service.py -v. Expected: FAIL before RuntimeService exists.
- [ ] Implement RuntimeService only as an adapter around MasterOrchestrator; do not add another state machine. Preserve durable state on runtime exceptions.
- [ ] Run focused tests. Expected: PASS.
- [ ] Commit: feat: wire orchestrator runtime service

### Task 3: Real CLI Entrypoint

**Files**
- Create: orchestrator/cli.py
- Test: orchestrator/tests/test_runtime_cli.py

**Interfaces**
- python -m orchestrator.cli submit <task.json>
- python -m orchestrator.cli status <task_id>
- python -m orchestrator.cli report <task_id>

- [ ] Write failing tests for submit/status/report, malformed JSON, and unknown task IDs; assert deterministic output/exit behavior and no mutation on invalid input.
- [ ] Run: pytest orchestrator/tests/test_runtime_cli.py -v. Expected: FAIL because entrypoint is absent.
- [ ] Implement a thin argparse-style CLI over RuntimeService; no arbitrary shell or exchange behavior.
- [ ] Run focused tests. Expected: PASS.
- [ ] Commit: feat: add orchestrator runtime cli

### Task 4: End-to-End Runtime Safety and Observation Tests

**Files**
- Modify: orchestrator/tests/test_runtime_service.py
- Create: orchestrator/tests/test_runtime_safety.py
- Modify: orchestrator/tests/test_status_documentation.py only if contract coverage requires it

- [ ] Add failing regressions for forbidden live actions, duplicate IDs, crash preservation, and reviewer-success-without-terminal-evidence.
- [ ] Run: pytest orchestrator/tests/test_runtime_safety.py -v. Expected: failures only for missing protections.
- [ ] Implement the minimal runtime-layer protections; do not weaken policy or add exchange behavior.
- [ ] Run: pytest orchestrator/tests -q. Expected: PASS.
- [ ] Commit: test: harden orchestrator runtime safety

### Task 5: Documentation and Observation Surface

**Files**
- Create: orchestrator/README.md
- Test: orchestrator/tests/test_runtime_docs.py
- Modify AGENTS.md or agent/SUBAGENT_WORKFLOW.md only if actual runtime behavior changes their existing contract.

- [ ] Write failing docs contract tests for submit/status/report, safety boundaries, and the statement that runtime completion is not merge/deploy/live trading.
- [ ] Run: pytest orchestrator/tests/test_runtime_docs.py -v.
- [ ] Write documentation from implemented interfaces only; include task envelope, observation, terminal states, failures, and PreFlight safety invariant.
- [ ] Run: pytest orchestrator/tests/test_runtime_docs.py orchestrator/tests -q. Expected: PASS.
- [ ] Commit: docs: document orchestrator runtime

### Task 6: Whole-Branch Verification, Review, and CI

**Files**
- Review all runtime files/tests from Tasks 1-5; no new production file expected.

- [ ] Run focused runtime tests: pytest orchestrator/tests/test_runtime_intake_store.py orchestrator/tests/test_runtime_service.py orchestrator/tests/test_runtime_cli.py orchestrator/tests/test_runtime_safety.py orchestrator/tests/test_runtime_docs.py -q.
- [ ] Run the repository's established full CI/test command and record exact result.
- [ ] Perform one independent whole-branch review for spec compliance, scope discipline, safety, evidence integrity, and regression quality. Critical/Important findings receive focused fix/re-review; do not batch unrelated fixes.
- [ ] Request GitHub CI and record run ID, head SHA, conclusion, and relevant jobs.
- [ ] Produce the final report with task ID, files, tests, CI, review, commits, remaining risk, and human action.
- [ ] Stop before merge. Merge remains an explicit human approval gate.

## Self-Review

Spec coverage maps directly to Tasks 1-6: intake/persistence, runtime wiring, real entrypoint, safety/observation, documentation, and final verification/review/CI. The plan preserves the existing state machine and dispatcher, pins terminal evidence requirements, covers the five review-focus failure classes, and explicitly excludes G8-PF031.

## Execution Handoff

ORCH-RUNTIME-001 is the bootstrap exception: the repository runtime cannot delegate this task to itself until the runtime exists. Therefore its implementation must use the established Superpowers subagent workflow as the bootstrap mechanism. Once merged, subsequent engineering tasks—including G8-PF031—must be submitted through the repository Master Orchestrator and delegated to its sub-agents.
