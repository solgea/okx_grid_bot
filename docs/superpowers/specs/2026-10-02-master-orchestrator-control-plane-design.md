# Master Orchestrator / Agent Control Plane — Design Specification

**Status:** Design approved in conversation; implementation not yet approved.  
**Target repository:** `solgea/okx_grid_bot`  
**Target branch:** `orchestrator/master-control-plane`

## 1. Purpose

Build a deterministic Master Orchestrator that manages engineering agents working on the OKX bot repository.

The orchestrator is a control plane, not a trading strategy. Its primary responsibility is to turn an approved engineering task into a controlled lifecycle:

`OBSERVE → DIAGNOSE → PLAN → POLICY CHECK → EXECUTE → VERIFY → COMMIT/REPORT → NEXT TASK`

The system must preserve human control over exchange-impacting and production-impacting actions.

## 2. Architecture

Initial implementation follows a multi-agent control-plane shape while keeping the boundaries compatible with a future hierarchical system.

```
MASTER ORCHESTRATOR
  ├── Planner Agent
  ├── Engineering Agent
  ├── Test Agent
  └── Reviewer Agent
          │
          ▼
     Execution Layer
     ├── Git
     ├── Tests
     └── CI
          │
          ▼
      OKX Bot Code
          │
          ▼
   Audit / Task State / Memory
```

The orchestrator owns task state and policy evaluation. Agents do not independently decide whether a restricted action is permitted.

## 3. Core Components

### 3.1 Orchestrator Core

Responsibilities:
- accept a task envelope;
- inspect repository/task state;
- select the next agent action;
- enforce allowed/forbidden actions;
- persist task state transitions;
- stop on policy violations or verification failures;
- emit an auditable execution report.

Core modules:

```
orchestrator/core/
├── orchestrator.py
├── task.py
├── state.py
├── policy.py
└── events.py
```

### 3.2 Agents

Each agent has one responsibility and communicates through explicit messages.

```
orchestrator/agents/
├── base.py
├── planner_agent.py
├── engineering_agent.py
├── test_agent.py
└── reviewer_agent.py
```

- **Planner Agent:** converts an approved objective into bounded execution steps.
- **Engineering Agent:** modifies repository code only within its task scope.
- **Test Agent:** runs focused and required verification.
- **Reviewer Agent:** checks diff, contract compliance, scope, and evidence.

No agent may bypass the orchestrator policy.

### 3.3 Execution Layer

```
orchestrator/execution/
├── dispatcher.py
├── git.py
└── ci.py
```

The execution layer provides controlled adapters for repository mutation, tests, commits, and CI observation.

## 4. Permission Model

Default engineering permissions:

```
READ_REPO
ANALYZE
PLAN
WRITE_CODE
RUN_TESTS
CREATE_COMMIT
REQUEST_CI
REPORT
```

Restricted actions require an explicit policy gate:

```
LIVE_ORDER
LIVE_WITHDRAWAL
LIVE_ACCOUNT_MUTATION
PRODUCTION_DEPLOY
POLICY_CHANGE
MERGE_PR
```

The initial orchestrator must default to deny for restricted actions.

No API key, exchange credential, or secret is exposed to an agent unless a future explicitly approved policy allows it.

## 5. Task Envelope

Tasks are immutable inputs to an execution cycle.

Example:

```json
{
  "task_id": "G8-PF031",
  "type": "engineering_fix",
  "priority": "blocking",
  "scope": "single_failure",
  "allowed_actions": [
    "read_repo",
    "modify_code",
    "run_tests",
    "commit"
  ],
  "forbidden_actions": [
    "live_exchange",
    "merge_pr",
    "deploy_production"
  ],
  "success_condition": "github_ci_pass"
}
```

The task state must record the original envelope, every state transition, agent action, verification result, and final disposition.

## 6. State Machine

Initial states:

```
RECEIVED
  ↓
OBSERVING
  ↓
DIAGNOSING
  ↓
PLANNING
  ↓
POLICY_CHECK
  ├── DENIED → BLOCKED
  └── ALLOWED
        ↓
      EXECUTING
        ↓
     VERIFYING
      ├── FAIL → DIAGNOSING
      └── PASS
            ↓
        REVIEWING
          ├── FAIL → DIAGNOSING
          └── PASS
                ↓
            COMMITTED
                ↓
             REPORTED
```

Terminal states:

- `BLOCKED`
- `COMMITTED`
- `REPORTED`

A verification failure does not silently advance the task.

## 7. Failure Handling

The orchestrator must:
1. capture the exact failing step;
2. preserve the failure evidence;
3. prevent unrelated scope expansion;
4. return the task to diagnosis;
5. allow a new bounded repair cycle;
6. re-run verification before completion.

For CI failures, the orchestrator records workflow/run identifiers and relevant failure output.

The current project convention of focused failure-driven repair is preserved, while allowing multiple independent failures only when the task envelope explicitly permits them.

## 8. Git / CI Policy

The orchestrator may:
- create an agent branch;
- modify files;
- create commits;
- observe CI;
- report CI evidence.

The orchestrator may not merge a PR or deploy production by default.

A successful task requires evidence, not an agent assertion.

Minimum completion evidence:
- expected files changed;
- tests executed;
- test result recorded;
- diff reviewed;
- CI status observed where CI is part of the task;
- no forbidden action occurred.

## 9. Audit / Memory

```
orchestrator/memory/
├── task_store.py
└── audit_log.py
```

The audit log records:
- task ID;
- timestamp;
- state transition;
- acting agent;
- requested action;
- policy decision;
- command/tool result;
- commit SHA;
- CI run ID/status;
- final outcome.

The memory layer is an execution record, not a source of authority. Policy remains authoritative.

## 10. Agent Protocol

```
orchestrator/protocols/
├── agent_protocol.py
└── messages.py
```

Every agent interaction must be structured around:
- task ID;
- agent ID;
- requested action;
- input context;
- expected output;
- evidence;
- status;
- next action.

Free-form agent output may be stored for diagnostics but cannot itself authorize restricted operations.

## 11. Configuration

```
orchestrator/config/
└── orchestrator.yaml
```

Configuration must define:
- enabled agents;
- action permissions;
- retry limits;
- verification requirements;
- CI requirements;
- restricted-action defaults.

Security-sensitive defaults are fail-closed.

## 12. Documentation / Status

The implementation will maintain:

```
MASTER_ORCHESTRATOR.md
AGENT_PROTOCOL.md
ORCHESTRATOR_POLICY.md
ORCHESTRATOR_STATUS.md
```

`ORCHESTRATOR_STATUS.md` is the human-readable execution state and must never claim completion without recorded verification evidence.

## 13. Testing Strategy

The orchestrator is developed test-first.

Required test layers:

1. **Domain tests**
   - task envelope validation;
   - state transitions;
   - permission evaluation.

2. **Agent contract tests**
   - valid/invalid agent messages;
   - forbidden action rejection;
   - deterministic task handoff.

3. **Execution adapter tests**
   - Git adapter behavior;
   - test execution;
   - CI result parsing.

4. **Orchestrator integration tests**
   - successful task lifecycle;
   - blocked task;
   - failed verification and retry;
   - reviewer rejection;
   - forbidden exchange action.

5. **Safety tests**
   - live order action denied by default;
   - production deploy denied by default;
   - merge denied by default;
   - missing evidence prevents completion.

No test may place a real exchange order.

## 14. Non-Goals for V1

V1 does not include:
- autonomous live trading;
- autonomous production deployment;
- autonomous PR merge;
- autonomous policy modification;
- unrestricted multi-agent parallelism;
- opaque long-running agent loops;
- LLM output as the source of truth for task state.

## 15. Success Criteria

The first implementation is successful when the orchestrator can take a bounded engineering task such as a G8 preflight blocker and deterministically:

1. register the task;
2. inspect repository state;
3. delegate planning;
4. authorize the engineering action;
5. execute the code change;
6. run tests;
7. observe CI;
8. request review;
9. record the commit and evidence;
10. report completion or block safely.

The orchestrator must remain able to stop at every gate.

## 16. Future Hierarchical Extension

The architecture intentionally leaves room for:

```
MASTER ORCHESTRATOR
  ├── Project Manager
  │     ├── Planner
  │     └── Scheduler
  ├── Engineering Manager
  │     ├── Engineering Agents
  │     └── Test Agents
  ├── Review Manager
  │     └── Reviewer Agents
  └── Safety Manager
        └── Policy / Risk Gates
```

This hierarchy is not required for V1. It becomes relevant only after the core control-plane lifecycle is stable and verified.
