# Phase Transition Approvals

## Current gate

- Phase A: **RUNNING / EVIDENCE COLLECTION**
- Phase B: **LOCKED**
- Live trading: **DISABLED**
- Emergency flatten: **DISABLED**

## Human authorization

The project owner has granted authority to execute controlled project steps without repeated approval prompts.

This authorization does **not** waive Demo Execution Contract gates. In particular, Phase B remains blocked until the contract's Phase-A acceptance criteria are objectively evidenced, including 3 consecutive UTC days, required tests, zero unexpected exchange order calls, zero unresolved incidents, and the required OKX verification record.

No Phase-B promotion approval is recorded here yet.

## Evidence records

Daily immutable evidence is written under `artifacts/phase_a/YYYY-MM-DD.json` by the scheduled Phase-A Shadow workflow. Missing days are not backfilled and cannot be marked PASS retrospectively.
