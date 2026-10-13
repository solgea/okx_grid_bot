# Phase A / G10–G16 Evidence Audit

**Audit baseline commit:** `04514196dcbf0a833faef01e768be309985c2231`  
**Baseline CI:** [Run #274](https://github.com/solgea/okx_grid_bot/actions/runs/38250649833) — completed / success  
**PR-head CI:** [Run #284](https://github.com/solgea/okx_grid_bot/actions/runs/38342779388) — completed / success on `3bf0a51d7a381df7fcddf28d67b21a1fa67726d1`  
**Scope:** documentation and evidence traceability only. No exchange orders, no runtime mode changes, and no gate promotion.

## Baseline CI evidence

Run #274 executed the following successful steps on the baseline commit:

- Compile
- Tests
- Docker build
- Docker runtime smoke (OKX Demo read-only)

Run #284 passed dependency installation, compile, tests, Docker build and Docker runtime smoke (OKX Demo read-only) for the PR head SHA above. These are repository CI checks, not proof that G10–G16 have passed, and do not establish three consecutive Phase A shadow days. Run #284 has no downloadable workflow artifact; runtime smoke is evidenced by the successful job step/log.

## Phase A: inspected repository records

The current `main` tree contains three date-named records for consecutive UTC calendar dates:

| UTC date | Recorded at (UTC) | Schema | Commit recorded in file | Counts (intent / NullTransport / journal) | Daily counters |
|---|---|---|---|---|---|
| 2026-10-10 | 2026-10-10T11:40:37.283015+00:00 | `phase-a-evidence.v1` | `a52de09fc91e6b44b36492ac16df85971b357a94` | 3 / 3 / 3 | incidents 0; mutation calls 0 |
| 2026-10-11 | 2026-10-11T05:39:37.673141+00:00 | `phase-a-evidence.v1` | `eca0b738e5cc8f5c2c4304078893c25560b1cfe1` | 3 / 3 / 3 | incidents 0; mutation calls 0 |
| 2026-10-12 | 2026-10-12T05:49:28.788215+00:00 | `phase-a-evidence.v1` | `99631ff90c37920efeb9ff188161d79a3b0a21b0` | 3 / 3 / 3 | incidents 0; mutation calls 0 |

Record links: [2026-10-10](../artifacts/phase_a/2026-10-10.json) · [2026-10-11](../artifacts/phase_a/2026-10-11.json) · [2026-10-12](../artifacts/phase_a/2026-10-12.json).

**Finding:** GitHub Actions history now links each date to a successful run whose `head_sha` matches the SHA embedded in that day's record. Run #7 was manually dispatched; runs #8 and #9 were scheduled. The workflow exposes **no downloadable artifacts** for these three runs; the JSON evidence was committed to the repository by the workflow. The records are schema v1 and predate the current workflow's v2 provenance assertions. They lack run ID, attempt, event, and current v2 provenance fields; the generator also uses date-scoped synthetic agents and explicitly sets `sequence_continuity_proven: false`. This establishes three successful dated synthetic workflow runs with internally matching counts, but **not** v2 evidence conformance or cross-day sequence continuity. Three-day acceptance remains **NOT VERIFIED**. Do not rewrite historical JSON to retrofit provenance.

## Read-only OKX result: repository copy reviewed

The committed record [okx-demo-assumptions-readonly-2026-10-12.json](../artifacts/phase_a/okx-demo-assumptions-readonly-2026-10-12.json) identifies tested commit `38a52b1bfff5d5814bc1c23d1ae453f4b872f3ce`, CI run [#38242245197](https://github.com/solgea/okx_grid_bot/actions/runs/38242245197), and read-only workflow run [#38242245161](https://github.com/solgea/okx_grid_bot/actions/runs/38242245161). The repository copy reports instrument metadata, position mode, funding-rate fields and pending-algo query as `OK`; fee rates, fills fee fields, funding bills and several execution semantics remain `NO_DATA`, `DOC_ONLY`, or `UNVERIFIED_READ_ONLY`.

The associated workflow run #9 job and artifact-upload step succeeded. Artifact `11743376138` was downloaded and inspected: ZIP member `okx-demo-assumptions-readonly.json` (2,108 bytes; SHA-256 `dbf09b69fd24c675bfec2f2d141e092213e58e0f718a32c92e9805c17eeb90b9`). The payload confirms `OK` for instrument metadata, position mode, funding rate and pending-algo query, while keeping `attach_algo_orders`, `demo_supports_attached_sl`, `duplicate_cl_ord_id_behavior`, and `reduce_only` as `UNVERIFIED_READ_ONLY`; fees/fill fees/funding bills are `NO_DATA`, and `cl_ord_id_rule` is `DOC_ONLY`. This verifies the artifact bytes and their recorded statuses only; it does not verify the unproven exchange behaviors. Do not upgrade any unverified field to PASS.

## Contract-to-evidence mapping

| Requirement | Current evidence source | Audit status | What remains unproven |
|---|---|---|---|
| Phase A evidence provenance and count consistency | `scripts/record_phase_a_evidence.py`, `tests/test_demo_phase_a_shadow.py`, `.github/workflows/phase-a-evidence.yml` | Runs #7/#8/#9 succeeded and match the records' embedded SHAs; each run has no downloadable artifact; counts are 3/3/3 | Current v2 provenance and cross-day sequence continuity; daily JSON remains v1 |
| OKX assumptions check is read-only | `scripts/okx_demo_assumptions_check.py`, `tests/test_okx_assumptions_check.py`, `.github/workflows/okx-demo-assumptions-readonly.yml` | Run #9 and artifact #11743376138 inspected; archive/member SHA recorded above; mock tests assert mutation calls are blocked | Live exchange semantics marked `UNVERIFIED_READ_ONLY` remain unproven; no mutating request may be used to prove assumptions |
| G8.6 preflight authorization | `agent/GATE_PLAN.md` and existing preflight implementation/tests | Gate requirement documented | Link each positive/negative preflight case to exact test and CI result |
| G10 order lifecycle (T09–T13) | `demo_exec/lifecycle.py`; `tests/test_demo_contract_gates.py` | PR-head CI #284 PASS on `3bf0a51d7a381df7fcddf28d67b21a1fa67726d1`; offline tests cover terminal cancel confirmation, fill-wins-cancel race (`PARTIAL`/`FILLED`), unresolved cancel → `UNKNOWN`, and terminal partial/fill/rejection states | State-machine tests do not prove real OKX cancel/fill semantics or partial-fill quantity accounting; delayed fill event after cancel confirmation is not demonstrated |
| G11 reconciliation (T14–T15) | Contract §8–10; `tests/test_demo_contract_gates.py` | PR-head CI #284 PASS on `3bf0a51d7a381df7fcddf28d67b21a1fa67726d1`; tests include `test_t14_mismatch_stops_without_repair`, `test_t15_unmanaged_order_is_untouched` | No real exchange reconciliation was run; live stale-state reconciliation remains unproven |
| G12 position integrity | Contract §5, §10 | Contract requirement specified | Explicit test/evidence for position size/state and protection deadline; no live order test |
| G13 risk / kill switch (T19–T22) | `engine/risk_manager.py`; `tests/test_g10_g16_offline_risk_gates.py` | PR-head CI #284 PASS on `3bf0a51d7a381df7fcddf28d67b21a1fa67726d1`; offline tests cover drawdown, daily-loss threshold, position-limit breach and latched kill switch | Emergency cleanup/flatten intentionally not invoked; contract-specific daily-loss accounting still needs separate review |
| G14 restart recovery (T25–T26) | Contract §8–10; `tests/test_demo_contract_gates.py` | PR-head CI #284 PASS on `3bf0a51d7a381df7fcddf28d67b21a1fa67726d1`; tests include `test_t25_recovery_is_paused`, `test_t26_corrupt_journal_blocks`, `test_t26_seq_gap_blocks` | No live restart/reconciliation scenario was run |
| G15 failure injection (T27) | Contract §10; `demo_exec/executor.py`; `tests/test_demo_contract_gates.py`; `tests/test_p1_3_canonical_risk_policy.py` | PR-head CI #284 PASS on `3bf0a51d7a381df7fcddf28d67b21a1fa67726d1`; offline connection-drop test classifies `TimeoutError`/`ConnectionError` as `UNKNOWN` without retry; stale market-data test asserts `PF025_STALE_MARKET_DATA` rejection | Duplicate/delayed response and stale-state/reconciliation injections remain missing |
| G16 Demo soak | Contract §10 | Acceptance requirement specified | Approved run window, per-order status/cleanup/reconciliation records and incident summary; do not perform a real order merely to close this evidence gap |

## Safety disposition

- Phase B remains **LOCKED**.
- `IS_DEMO` and read-only checks are not substitutes for Phase A acceptance.
- No live trading, no order-placement test, and no Emergency Flatten action is authorized by this audit.
- Do not mark G10–G16 PASS or Phase 3 FROZEN from a green generic CI run.
- Preserve `UNVERIFIED_READ_ONLY`, `NO_DATA`, and `DOC_ONLY` statuses unless the specific claim is supported by its required evidence.
- Historical evidence artifacts are immutable for this audit; missing provenance is documented as a gap, not patched into old records.

## Next evidence-only work

1. Preserve the run-to-record mapping above; the three historical Phase A runs have no downloadable artifacts, so do not fabricate artifact IDs or alter the v1 JSON.
2. Link each remaining G10–G16 test ID to its exact function and eventual CI run/SHA. G12 position/protection deadline, duplicate/delayed response, stale-state reconciliation and G16 soak evidence remain gaps.
3. PR-head CI #284 is recorded above against the exact tested SHA. If this audit-document correction is committed, rerun CI and record that new SHA/run as well. Execution tests use `NullTransport`; risk and preflight tests use offline fixtures; no exchange call is introduced.
4. Re-evaluate gate acceptance only after all required evidence and required human approval are present.
