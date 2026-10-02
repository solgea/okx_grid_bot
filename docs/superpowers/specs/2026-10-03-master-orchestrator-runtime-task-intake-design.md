# Master Orchestrator Runtime & Task Intake Design

## Status

**Approved design:** 2026-10-03  
**Task:** ORCH-RUNTIME-001  
**Repository:** solgea/okx_grid_bot  
**Base:** main

## Goal

Turn the existing Master Orchestrator control-plane core into a runnable, observable task runtime without changing the existing agent safety boundaries or implementing G8-PF031 itself.

The runtime must accept a validated task envelope, execute the existing orchestrator lifecycle through its configured Planner/Engineering/Test/Reviewer dispatchers, persist an auditable task/state trail, and expose a human-readable status/report surface.

## Scope

### In scope

- Runtime service adapter around the existing `MasterOrchestrator`.
- Validated task intake.
- CLI entrypoint for submitting and observing tasks.
- Persistent task state and audit events sufficient for restart-safe observation of a task record.
- Human-readable status/report output.
- Integration tests proving intake → orchestrator lifecycle → audit/report.
- Documentation for running and observing the runtime.

### Explicitly out of scope

- G8-PF031 implementation.
- Live exchange access or live order placement.
- Production deployment.
- Autonomous PR merge.
- Policy changes.
- A new agent framework.
- Replacing the existing `ActionDispatcher` or `MasterOrchestrator`.
- GitHub Issue automation.
- Web UI/dashboard.
- Autonomous scheduling or unrestricted parallel task execution.

## Existing architecture

The existing control plane provides:

- `MasterOrchestrator.submit(task)`
- `MasterOrchestrator.step(task_id)`
- `MasterOrchestrator.run(task_id)`
- `MasterOrchestrator.report(task_id)`
- `ActionDispatcher` for agent dispatch.
- Fail-closed policy evaluation.
- Explicit commit evidence before `COMMITTED`.

The runtime must adapt to these interfaces rather than duplicate lifecycle logic.

## Runtime architecture

```
Task JSON / CLI
      |
      v
Task Intake
      |
      v
Runtime Service
      |
      +--> Task Store
      |
      +--> MasterOrchestrator
      |       |
      |       +--> Planner
      |       +--> Engineering
      |       +--> Test
      |       +--> Reviewer
      |
      +--> Audit / Status
```

### Components

#### 1. Task intake

A small validation boundary accepts the repository task envelope and rejects malformed or unsafe requests before orchestration.

Minimum task identity fields:

- `task_id`
- `type`
- `priority`
- `scope`
- `allowed_actions`
- `forbidden_actions`
- `success_condition`

The intake layer must not grant capabilities that the policy engine forbids.

#### 2. Runtime service

The runtime service owns the operational lifecycle:

1. accept task;
2. persist task;
3. invoke `MasterOrchestrator.submit()`;
4. invoke bounded orchestration;
5. persist state/evidence after each transition;
6. expose final status/report.

The runtime must not implement a second state machine.

#### 3. Observation state

The runtime writes a stable observation record for each task containing:

- task ID;
- current state;
- state transition history;
- current/last agent role;
- action;
- policy decision;
- evidence;
- test command/result;
- commit SHA when available;
- CI reference/status when available;
- review verdict;
- final outcome;
- remaining risk.

Human-readable state is exposed through `STATE.md`-style output or an equivalent CLI report. Machine-readable audit events use JSON Lines.

#### 4. Persistence

Use a simple local persistence mechanism compatible with the existing repository and tests. The first implementation should avoid introducing an external database.

Requirements:

- deterministic;
- local;
- append-safe for audit events;
- readable without the runtime;
- test-isolatable via temporary directories.

The persistence boundary must be abstract enough that a future database adapter can replace it without changing task intake or orchestration contracts.

#### 5. CLI

Provide a real Python module entrypoint:

```bash
python -m orchestrator.cli submit <task.json>
python -m orchestrator.cli status <task_id>
python -m orchestrator.cli report <task_id>
```

The CLI is an observation/control interface, not a trading interface.

`submit` must print the accepted task ID and initial state.

`status` must print the current state and latest evidence.

`report` must print the complete summarized lifecycle, including audit count and terminal outcome.

No CLI command may place an exchange order, alter live exchange state, merge a PR, deploy production, or change policy.

## State model

The runtime must preserve the existing state machine:

```
RECEIVED
  -> OBSERVING
  -> DIAGNOSING
  -> PLANNING
  -> POLICY_CHECK
  -> EXECUTING
  -> VERIFYING
  -> REVIEWING
  -> COMMITTED
  -> REPORTED
```

Failure remains terminal at `BLOCKED` unless the orchestrator explicitly supports another controlled transition.

The runtime must never report `COMMITTED` without actual commit evidence.

The runtime must never report successful verification without Test Agent verification evidence.

## Agent dispatch

The runtime uses the repository's existing dispatcher contract.

Expected roles:

- `planner`
- `engineering`
- `test`
- `reviewer`

Each task is still single-scope. The runtime must not fan out unrelated tasks or permit an agent to self-assign another blocker.

## Safety contract

The following remain hard-denied:

- live exchange actions;
- live orders;
- live account mutation;
- production deployment;
- policy changes;
- autonomous merge.

For OKX work:

```
PreFlight != AUTHORIZED
        |
        +--> not permission to submit an exchange order
```

Runtime execution is therefore safe to exercise with test doubles and repository-local fixtures only.

## Failure handling

- Invalid task envelope: reject before orchestration.
- Policy denial: persist denial and enter `BLOCKED`.
- Agent blocked: persist evidence and enter `BLOCKED`.
- Test verification failure: preserve evidence and return to the existing controlled diagnosis path.
- Reviewer failure: preserve evidence and return to the existing controlled diagnosis path.
- Missing commit evidence: `BLOCKED`.
- Runtime exception: preserve the last durable task/audit state and exit non-zero.

No broad exception swallowing.

## Testing requirements

The implementation must include tests for:

1. valid task intake;
2. invalid task rejection;
3. forbidden capability rejection;
4. submit creates an observable task;
5. runtime executes the lifecycle using injected test doubles;
6. Planner/Engineering/Test/Reviewer dispatch is observable;
7. audit events are persisted in order;
8. `status` reports the current state;
9. `report` includes terminal outcome and evidence;
10. verification without explicit Test Agent pass cannot reach `COMMITTED`;
11. missing commit evidence cannot reach `COMMITTED`;
12. runtime remains unable to perform live exchange actions.

A dedicated G8-PF031 regression test is not part of this task.

## Observability contract

At minimum, a completed task must allow a human to answer:

- What task was received?
- What state is it in?
- Which agent acted last?
- What action was requested?
- What did policy decide?
- What tests ran and what happened?
- What reviewer decided?
- What commit was produced?
- Why did the task terminate?
- What risk remains?
- What human action, if any, is required?

## Completion gate

ORCH-RUNTIME-001 is complete only when:

- a real entrypoint exists;
- a task can be submitted without directly constructing Python objects;
- the task can be observed through the runtime;
- the full lifecycle is covered by deterministic integration tests;
- audit/state output is persisted;
- focused tests pass;
- full repository CI passes;
- independent review passes;
- commit and CI evidence are recorded.

Completion does not imply merge, production deployment, live trading, or G8 gate closure. Merge remains a separate explicit human approval gate.

## Future extension

After this runtime is merged, G8-PF031 may be submitted through the runtime and delegated to the repository's Engineering/Test/Reviewer agents. GitHub Issue automation and a web dashboard can be considered separately after the core runtime proves stable.
