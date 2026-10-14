# Phase A Daily Shadow Evidence Contract

**Schema:** `phase-a-evidence.v3`  
**Scope:** deterministic, offline Phase A shadow validation only. This contract does not authorize exchange orders or Phase B.

## Immutable run identity

Each workflow attempt writes exactly one JSON record at:

```text
artifacts/phase_a/YYYY-MM-DD-run-GITHUB_RUN_ID-attempt-GITHUB_RUN_ATTEMPT.json
```

The date is UTC. `workflow_run_id` and `workflow_run_attempt` must match the GitHub Actions environment, and `evidence_id` must equal the basename above. `git_sha` must equal `GITHUB_SHA`; `workflow_event` must equal `GITHUB_EVENT_NAME` and be either `schedule` or `workflow_dispatch`.

The writer uses exclusive file creation. If the exact evidence path already exists, it fails closed rather than overwriting it. A rerun gets a distinct attempt identity. Historical date-only records, including `artifacts/phase_a/2026-10-14.json`, are retained byte-for-byte and are not retrofitted with new provenance.

## Required acceptance conditions

A record is acceptable only when all of the following are true:

- Schema is `phase-a-evidence.v3`, phase is `A`, and transport is `NullTransport`.
- `exchange_touched=false`, `exchange_mutation_calls=0`, and the structural exchange-order-call observation is zero.
- `intent_count = null_transport_place_calls = journal_event_count = 3` and `counts_consistent=true`.
- `acceptance.daily_shadow_run=true` and `acceptance.null_transport_only=true`.
- `acceptance.unexpected_exchange_order_calls=0`, `acceptance.unresolved_incidents=0`, and `incidents=[]`.
- `sequence_scope=daily_synthetic_validation` and `sequence_continuity_proven=false`. A daily synthetic record must not claim cross-run or production-journal continuity.

The order-call observation is explicitly structural: NullTransport has no exchange client. It is not external network telemetry and must not be represented as proof of real exchange behavior.

## Local tests

Local test records use `workflow_run_id=local`, `workflow_run_attempt=local`, `git_sha=local`, and `workflow_event=local`. This local-only exception is accepted by the Python validator but is not accepted by the GitHub Actions provenance step.

## Gate disposition

A successful Phase A workflow validates the shadow-evidence contract only. It does not by itself establish three consecutive accepted days, prove sequence continuity, validate live OKX semantics, pass G10–G16, unlock Phase B, or authorize live trading.
