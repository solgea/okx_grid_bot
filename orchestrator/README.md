# Master Orchestrator Runtime

The runtime is a local control-plane adapter around the existing MasterOrchestrator. It accepts validated task envelopes and exposes observation commands; it is not a trading interface.

## Commands

Submit a task:

    python -m orchestrator.cli --root .orchestrator submit task.json

Run an accepted task:

    python -m orchestrator.cli --root .orchestrator run <task_id>

Observe status:

    python -m orchestrator.cli --root .orchestrator status <task_id>

Read the lifecycle report:

    python -m orchestrator.cli --root .orchestrator report <task_id>

The task file must contain task_id, type, priority, scope, allowed_actions, forbidden_actions, and success_condition.

## Safety

The intake fails closed for restricted capabilities such as live orders, live exchange/account mutation, production deployment, policy changes, and merge authority. Runtime completion does not authorize merge, deployment, live trading, or close G8/G9.

For OKX execution, **PreFlight != AUTHORIZED is never permission to submit an exchange order.**

The runtime does not provide arbitrary shell execution and does not expose exchange credentials or order operations.

## Observation

Task state is persisted under the configured root, with one task record per task and an append-ordered EVENTS.jsonl audit log. The persistence format is readable without the runtime and is isolated by --root for tests.

## Lifecycle

The runtime delegates the existing lifecycle to MasterOrchestrator:

RECEIVED -> OBSERVING -> DIAGNOSING -> PLANNING -> POLICY_CHECK -> EXECUTING -> VERIFYING -> REVIEWING -> COMMITTED -> REPORTED

Policy, agent, verification, reviewer, and commit failures remain visible as BLOCKED or controlled diagnosis transitions. COMMITTED requires explicit commit evidence and successful verification evidence.
