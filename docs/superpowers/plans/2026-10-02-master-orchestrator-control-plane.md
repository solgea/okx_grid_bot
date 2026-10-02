# Master Orchestrator / Agent Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Master Orchestrator V1 that registers engineering tasks, delegates bounded work to agents, enforces fail-closed permissions, verifies evidence, and records an auditable lifecycle without performing live exchange actions.

**Architecture:** Implement a small control-plane core with typed task/state/policy/event contracts, agent adapters, execution adapters, audit persistence, and integration tests. Keep agent implementations deterministic and replaceable; the orchestrator owns authorization and terminal-state decisions.

**Tech Stack:** Python 3.11+, existing repository test stack (pytest/pytest-asyncio where already used), standard-library-first orchestrator implementation, YAML configuration only if the repository already provides the dependency; otherwise use a typed Python configuration object for V1.

**Spec:** `docs/superpowers/specs/2026-10-02-master-orchestrator-control-plane-design.md`

## Global Constraints

- No live exchange execution.
- Restricted actions are denied by default.
- Agent output never authorizes restricted operations.
- Task state is authoritative over free-form agent output.
- Verification evidence is required before completion.
- V1 must not merge PRs, deploy production, place live orders, mutate live accounts, or modify policy.
- Orchestrator modules must be independently testable.
- Changes remain scoped to the orchestrator subsystem and its tests/docs.

## Review Focus

- **Unknown action:** an unrecognized action must be denied rather than implicitly allowed; covered by policy tests.
- **Missing evidence:** a task must not reach a completed/reportable state without required verification evidence; covered by state/integration tests.
- **Agent failure:** an agent exception or invalid response must produce a controlled failed/blocked transition rather than silently advancing; covered by protocol/integration tests.
- **Duplicate task/event:** repeated identifiers must not create ambiguous state; covered by task/event tests.
- **Forbidden exchange action:** live order/account actions must remain denied even when an agent requests them; covered by safety tests.

---

### Task 1: Establish the orchestrator contracts

**Files:**
- Create: `orchestrator/__init__.py`
- Create: `orchestrator/core/__init__.py`
- Create: `orchestrator/core/task.py`
- Create: `orchestrator/core/state.py`
- Create: `orchestrator/core/policy.py`
- Test: `orchestrator/tests/test_core_contracts.py`

**Interfaces:**
- `TaskEnvelope`: immutable task definition containing `task_id`, `type`, `priority`, `scope`, `allowed_actions`, `forbidden_actions`, and `success_condition`.
- `TaskState`: `RECEIVED, OBSERVING, DIAGNOSING, PLANNING, POLICY_CHECK, EXECUTING, VERIFYING, REVIEWING, COMMITTED, REPORTED, BLOCKED`.
- `PolicyDecision`: allow/deny result plus reason.
- `PolicyEngine.evaluate(task, action) -> PolicyDecision`.

- [ ] **Step 1: Write failing contract tests** for immutable task fields, valid state values, and fail-closed policy behavior.
- [ ] **Step 2: Run** `pytest orchestrator/tests/test_core_contracts.py -v`; expected: FAIL because contracts do not exist.
- [ ] **Step 3: Implement** the minimal typed contracts. Use immutable dataclasses/enums and normalize actions to explicit strings/enums.
- [ ] **Step 4: Run** the focused tests; expected: PASS.
- [ ] **Step 5: Commit** `feat: add orchestrator core contracts`.

### Task 2: Add structured agent protocol and messages

**Files:**
- Create: `orchestrator/protocols/__init__.py`
- Create: `orchestrator/protocols/messages.py`
- Create: `orchestrator/protocols/agent_protocol.py`
- Test: `orchestrator/tests/test_agent_protocol.py`

**Interfaces:**
- `AgentRequest(task_id, agent_id, action, context) -> AgentRequest`.
- `AgentResult(task_id, agent_id, status, evidence, next_action) -> AgentResult`.
- `AgentProtocol.validate_request(request) -> None`.
- `AgentProtocol.validate_result(result) -> None`.

- [ ] **Step 1: Write failing tests** for valid requests/results, task-ID mismatch, unknown status, and missing evidence on successful verification.
- [ ] **Step 2: Run focused tests; expected: FAIL.**
- [ ] **Step 3: Implement typed messages and validation without allowing free-form result text to authorize actions.
- [ ] **Step 4: Run focused tests; expected: PASS.**
- [ ] **Step 5: Commit** `feat: add orchestrator agent protocol`.

### Task 3: Add event and audit contracts

**Files:**
- Create: `orchestrator/core/events.py`
- Create: `orchestrator/memory/__init__.py`
- Create: `orchestrator/memory/audit_log.py`
- Create: `orchestrator/memory/task_store.py`
- Test: `orchestrator/tests/test_audit_and_state_store.py`

**Interfaces:**
- `OrchestratorEvent(event_id, task_id, timestamp, event_type, actor, payload)`.
- `AuditLog.append(event) -> None`.
- `AuditLog.events(task_id) -> list[OrchestratorEvent]`.
- `TaskStore.create(task) -> None`.
- `TaskStore.get(task_id) -> TaskRecord | None`.
- `TaskStore.transition(task_id, new_state, evidence=None) -> TaskRecord`.

- [ ] **Step 1: Write failing tests** for append/read, duplicate event IDs, unknown task rejection, and legal state transitions.
- [ ] **Step 2: Run focused tests; expected: FAIL.**
- [ ] **Step 3: Implement an in-memory V1 store. Keep persistence out of scope; make the interfaces replaceable for later SQLite/Postgres storage.
- [ ] **Step 4: Run focused tests; expected: PASS.**
- [ ] **Step 5: Commit** `feat: add orchestrator audit and task state stores`.

### Task 4: Add agent interfaces and deterministic V1 agents

**Files:**
- Create: `orchestrator/agents/__init__.py`
- Create: `orchestrator/agents/base.py`
- Create: `orchestrator/agents/planner_agent.py`
- Create: `orchestrator/agents/engineering_agent.py`
- Create: `orchestrator/agents/test_agent.py`
- Create: `orchestrator/agents/reviewer_agent.py`
- Test: `orchestrator/tests/test_agents.py`

**Interfaces:**
- `Agent.handle(request: AgentRequest) -> AgentResult`.
- `PlannerAgent.handle(...) -> AgentResult` produces bounded execution steps.
- `EngineeringAgent.handle(...) -> AgentResult` only returns an execution request/result; it does not self-authorize restricted actions.
- `TestAgent.handle(...) -> AgentResult` reports verification evidence.
- `ReviewerAgent.handle(...) -> AgentResult` reports review evidence.

- [ ] **Step 1: Write failing tests** for deterministic routing, task-ID preservation, and rejection of an agent result that attempts to authorize a forbidden action.
- [ ] **Step 2: Run focused tests; expected: FAIL.**
- [ ] **Step 3: Implement minimal agents as protocol adapters. V1 agents do not contain an LLM; they provide deterministic contracts around future agent backends.
- [ ] **Step 4: Run focused tests; expected: PASS.**
- [ ] **Step 5: Commit** `feat: add orchestrator agent interfaces`.

### Task 5: Add execution adapters

**Files:**
- Create: `orchestrator/execution/__init__.py`
- Create: `orchestrator/execution/dispatcher.py`
- Create: `orchestrator/execution/git.py`
- Create: `orchestrator/execution/ci.py`
- Test: `orchestrator/tests/test_execution_adapters.py`

**Interfaces:**
- `ActionDispatcher.dispatch(task, request) -> AgentResult`.
- `GitExecutor` exposes read/branch/commit operations required by V1.
- `TestExecutor.run(command) -> VerificationEvidence`.
- `CIExecutor.status(commit_sha) -> VerificationEvidence`.

- [ ] **Step 1: Write failing adapter tests** using fakes; assert no live-exchange action is dispatchable and subprocess failures are surfaced as evidence.
- [ ] **Step 2: Run focused tests; expected: FAIL.**
- [ ] **Step 3: Implement adapters behind interfaces. Use subprocess only for explicitly allowlisted local test/git commands; never expose arbitrary shell execution through agent messages.
- [ ] **Step 4: Run focused tests; expected: PASS.**
- [ ] **Step 5: Commit** `feat: add orchestrator execution adapters`.

### Task 6: Implement the Master Orchestrator lifecycle

**Files:**
- Create: `orchestrator/core/orchestrator.py`
- Test: `orchestrator/tests/test_orchestrator_lifecycle.py`

**Interfaces:**
- `MasterOrchestrator.submit(task: TaskEnvelope) -> TaskRecord`.
- `MasterOrchestrator.step(task_id: str) -> TaskRecord`.
- `MasterOrchestrator.run(task_id: str) -> TaskRecord`.
- `MasterOrchestrator.report(task_id: str) -> dict`.

- [ ] **Step 1: Write failing integration tests** for a successful bounded engineering lifecycle, policy denial, verification failure, reviewer rejection, and final evidence-gated completion.
- [ ] **Step 2: Run focused tests; expected: FAIL.**
- [ ] **Step 3: Implement the state machine exactly as specified: `RECEIVED → OBSERVING → DIAGNOSING → PLANNING → POLICY_CHECK → EXECUTING → VERIFYING → REVIEWING → COMMITTED → REPORTED`; failure returns to `DIAGNOSING`, restricted actions transition to `BLOCKED`.
- [ ] **Step 4: Run focused tests; expected: PASS.**
- [ ] **Step 5: Commit** `feat: implement master orchestrator lifecycle`.

### Task 7: Add configuration and safety defaults

**Files:**
- Create: `orchestrator/config/__init__.py`
- Create: `orchestrator/config/orchestrator.yaml`
- Create: `orchestrator/config/loader.py`
- Test: `orchestrator/tests/test_orchestrator_config.py`

**Interfaces:**
- `load_config(path=None) -> OrchestratorConfig`.
- `OrchestratorConfig` must default restricted actions to denied and require verification evidence.

- [ ] **Step 1: Write failing configuration tests** for default-deny restrictions, retry limits, enabled agents, and verification requirements.
- [ ] **Step 2: Run focused tests; expected: FAIL.**
- [ ] **Step 3: Implement configuration loading using a dependency already present in the repository; if no YAML dependency exists, use a minimal typed default configuration and add YAML parsing only after explicit dependency verification.
- [ ] **Step 4: Run focused tests; expected: PASS.**
- [ ] **Step 5: Commit** `feat: add orchestrator safety configuration`.

### Task 8: Add documentation and human-readable status

**Files:**
- Create: `MASTER_ORCHESTRATOR.md`
- Create: `AGENT_PROTOCOL.md`
- Create: `ORCHESTRATOR_POLICY.md`
- Create: `ORCHESTRATOR_STATUS.md`
- Test: `orchestrator/tests/test_status_documentation.py`

- [ ] **Step 1: Write failing documentation/status tests** for required permission names, state names, and no false completion claim.
- [ ] **Step 2: Implement the four documents and status renderer.
- [ ] **Step 3: Run focused documentation tests; expected: PASS.
- [ ] **Step 4: Commit** `docs: document orchestrator control plane`.

### Task 9: Full verification and V1 safety gate

**Files:**
- Modify only if required by a failing test.

- [ ] **Step 1: Run all orchestrator tests.**
- [ ] **Step 2: Run the repository's existing test suite to prove no regression.**
- [ ] **Step 3: Run compile/static checks already used by CI.
- [ ] **Step 4: Verify no restricted action can be reached without policy approval.
- [ ] **Step 5: Record commit SHAs and verification evidence in `ORCHESTRATOR_STATUS.md`.
- [ ] **Step 6: Commit the final status only after all required checks pass.**

## Definition of Done

V1 is complete only when all of the following are evidenced:
- all orchestrator tests pass;
- existing repository tests pass;
- compile/static checks pass;
- task lifecycle reaches `REPORTED` only with verification/review evidence;
- restricted actions are denied by default;
- duplicate IDs and invalid agent messages are handled deterministically;
- no live exchange action is executed;
- documentation and status reflect the actual verified state.
