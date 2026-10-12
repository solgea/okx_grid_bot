# Phase A Contract Test Evidence Map

Status: **Required test set verified on code commit `38a52b1bfff5d5814bc1c23d1ae453f4b872f3ce`**. This map identifies the contract test(s) for every Phase A-required test ID. The successful CI run below executed the full test suite and read-only runtime smoke check.

Safety scope: unit tests use `NullTransport`, in-memory/fake objects, and isolated temporary journal files. The test suite must not invoke the legacy `scripts/g9_demo_order.py` CLI. No order placement, cancellation, leverage change, or margin-mode change is permitted in this workflow.

| Contract ID | Test identity | Coverage / expected result |
|---|---|---|
| T01 | `tests/test_demo_contract_gates.py::test_t01_non_demo_submit_is_rejected_before_transport` | `is_demo=False` returns `E_NOT_DEMO`; NullTransport call count remains 0 |
| T02 | `tests/test_demo_contract_gates.py::test_t02_create_order_only_transport` | Static scan restricts `create_order` to approved transport modules |
| T03 | `tests/test_demo_contract_gates.py::test_t03_phase_a_rejects_real_transport` | Phase A cannot construct OKX transport |
| T04 | `tests/test_execution_authorization.py::test_rejected_preflight_cannot_reach_execution_boundary`; `tests/test_execution_safety.py::test_preflight_rejects_stale_market` | Rejected/stale preflight does not cross execution boundary |
| T05 | `tests/test_demo_phase_a_shadow.py::test_duplicate_agent_seq_is_rejected` | Duplicate `(agent_id, seq)` returns `E_JOURNAL` |
| T06 | `tests/test_demo_contract_gates.py::test_t06_journal_prevents_seq_reuse_after_restart` | Restarted executor reads the journal and rejects reuse of the same `(agent_id, seq)` without another transport call |
| T07 | `tests/test_demo_contract_gates.py::test_t07_timeout_records_unknown_and_does_not_retry` | Simulated NullTransport timeout returns UNKNOWN and the same intent is not sent again |
| T08 | `tests/test_demo_contract_gates.py::test_t08_unresolved_unknown_stops_agent` | A simulated unresolved UNKNOWN blocks a subsequent intent; no further transport call occurs |
| T14 | `tests/test_demo_contract_gates.py::test_t14_mismatch_stops_without_repair` | Reconciliation mismatch stops; no auto-repair |
| T15 | `tests/test_demo_contract_gates.py::test_t15_unmanaged_order_is_untouched` | Unmanaged order is ignored and not modified |
| T23 | `tests/test_demo_contract_gates.py::test_t23_failed_promotion_stays_paper` | Failed promotion remains PAPER |
| T24 | `tests/test_demo_contract_gates.py::test_t24_promotion_preserves_seq` | Promotion preserves sequence |
| T25 | `tests/test_demo_contract_gates.py::test_t25_recovery_is_paused` | Restart recovery returns RECOVERED_PAUSED |
| T26 | `tests/test_demo_contract_gates.py::test_t26_corrupt_journal_blocks`; `tests/test_demo_contract_gates.py::test_t26_seq_gap_blocks` | Corrupt journal and sequence gap block recovery |

## Evidence record

- Tested code commit SHA: `38a52b1bfff5d5814bc1c23d1ae453f4b872f3ce`.
- CI run #260: https://github.com/solgea/okx_grid_bot/actions/runs/38242245197 — **PASS**, 205 tests passed; compile, Docker build, and read-only OKX runtime smoke passed.
- OKX assumptions workflow run #9: https://github.com/solgea/okx_grid_bot/actions/runs/38242245161 — **PASS** (`summary.failed=[]`). The result contains explicit `NO_DATA` / `UNVERIFIED_READ_ONLY` items; these are not rewritten as PASS.
- Committed Section 11 record: `artifacts/phase_a/okx-demo-assumptions-readonly-2026-10-12.json`.
- Artifact copy: https://github.com/solgea/okx_grid_bot/actions/runs/38242245161/artifacts/11743376138
- Phase A acceptance: **NOT GRANTED by this map alone**. The three consecutive daily records, zero unexpected mutation calls, zero unresolved incidents, and committed Section 11 record must still be reviewed together on the target branch.
