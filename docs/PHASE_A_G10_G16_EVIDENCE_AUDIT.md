# Phase A / G10–G16 Evidence Audit

**Audit baseline commit:** `04514196dcbf0a833faef01e768be309985c2231`  
**Baseline CI:** [Run #274](https://github.com/solgea/okx_grid_bot/actions/runs/38250649833) — completed / success  
**Scope:** documentation and evidence traceability only. No exchange orders, no runtime mode changes, and no gate promotion.

## Baseline CI evidence

Run #274 executed the following successful steps on the baseline commit:

- Compile
- Tests
- Docker build
- Docker runtime smoke (OKX Demo read-only)

This is repository CI evidence. It is **not** evidence that G10–G16 have passed, nor does it establish three consecutive Phase A shadow days.

## Phase A: inspected repository records

The current `main` tree contains three date-named records for consecutive UTC calendar dates:

| UTC date | Recorded at (UTC) | Schema | Commit recorded in file | Counts (intent / NullTransport / journal) | Daily counters |
|---|---|---|---|---|---|
| 2026-10-10 | 2026-10-10T11:40:37.283015+00:00 | `phase-a-evidence.v1` | `a52de09fc91e6b44b36492ac16df85971b357a94` | 3 / 3 / 3 | incidents 0; mutation calls 0 |
| 2026-10-11 | 2026-10-11T05:39:37.673141+00:00 | `phase-a-evidence.v1` | `eca0b738e5cc8f5c2c4304078893c25560b1cfe1` | 3 / 3 / 3 | incidents 0; mutation calls 0 |
| 2026-10-12 | 2026-10-12T05:49:28.788215+00:00 | `phase-a-evidence.v1` | `99631ff90c37920efeb9ff188161d79a3b0a21b0` | 3 / 3 / 3 | incidents 0; mutation calls 0 |

Record links: [2026-10-10](../artifacts/phase_a/2026-10-10.json) · [2026-10-11](../artifacts/phase_a/2026-10-11.json) · [2026-10-12](../artifacts/phase_a/2026-10-12.json).

**Finding:** the repository contains records for three consecutive UTC dates, and each record reports internally matching counts and zero incidents. However, these are schema v1 records and do not contain workflow run ID, attempt, event, or the v2 provenance fields asserted by the current workflow. The current evidence-generation code explicitly sets `sequence_continuity_proven: false` and uses date-scoped synthetic agents. Therefore, these records establish three dated daily synthetic runs, **not** cross-day sequence continuity or full current-workflow provenance. The three-day acceptance criterion remains **NOT VERIFIED** until each date is linked to its authentic workflow run/artifact and validated against the current acceptance contract. Historical records must not be rewritten to retrofit missing provenance.

## Read-only OKX result: repository copy reviewed

The committed record [okx-demo-assumptions-readonly-2026-10-12.json](../artifacts/phase_a/okx-demo-assumptions-readonly-2026-10-12.json) identifies tested commit `38a52b1bfff5d5814bc1c23d1ae453f4b872f3ce`, CI run [#38242245197](https://github.com/solgea/okx_grid_bot/actions/runs/38242245197), and read-only workflow run [#38242245161](https://github.com/solgea/okx_grid_bot/actions/runs/38242245161). The repository copy reports instrument metadata, position mode, funding-rate fields and pending-algo query as `OK`; fee rates, fills fee fields, funding bills and several execution semantics remain `NO_DATA`, `DOC_ONLY`, or `UNVERIFIED_READ_ONLY`.

The associated workflow run has a successful job and an artifact metadata entry, but artifact metadata and job success are not the same as independently inspecting the downloadable artifact bytes. The actual downloadable workflow artifact has **not** been independently verified in this audit. Do not upgrade any unverified field to PASS.

## Contract-to-evidence mapping

| Requirement | Current evidence source | Audit status | What remains unproven |
|---|---|---|---|
| Phase A evidence provenance and count consistency | `scripts/record_phase_a_evidence.py`, `tests/test_demo_phase_a_shadow.py`, `.github/workflows/phase-a-evidence.yml` | Daily v1 records show matching counts; current script has provenance checks | Authentic run/artifact links for each date; current v2 provenance and three-day continuity acceptance |
| OKX assumptions check is read-only | `scripts/okx_demo_assumptions_check.py`, `tests/test_okx_assumptions_check.py`, `.github/workflows/okx-demo-assumptions-readonly.yml` | Mock tests cover read-only hardening; workflow run/job reports success; repository result contains explicit unverified fields | Independently inspect actual workflow artifact bytes; no mutating request may be used to prove assumptions |
| G8.6 preflight authorization | `agent/GATE_PLAN.md` and existing preflight implementation/tests | Gate requirement documented | Link each positive/negative preflight case to exact test and CI result |
| G10 order lifecycle (T09–T13) | `docs/DEMO_EXECUTION_CONTRACT.md` §4, §9; `tests/test_demo_contract_gates.py` | T07/T08 timeout and UNKNOWN safeguards are represented by deterministic tests | T09–T13 cancel confirmation, cancel/fill race, partial fill, rejection and duplicate/delayed response evidence are not demonstrated by the inspected test file |
| G11 reconciliation (T14–T15) | Contract §8–10; `tests/test_demo_contract_gates.py` | T14 mismatch fail-stop and T15 unmanaged-order ignore tests exist | Preserve test-run evidence tied to the exact PR SHA |
| G12 position integrity | Contract §5, §10 | Contract requirement specified | Explicit test/evidence for position size/state and protection deadline; no live order test |
| G13 risk / kill switch (T19–T22) | Contract §6, §9–10 | Contract scenarios specified | Exact deterministic threshold, hard-stop, cleanup and kill-switch tests/results are not demonstrated by the inspected test file |
| G14 restart recovery (T25–T26) | Contract §8–10; `tests/test_demo_contract_gates.py` | T25 paused recovery and T26 corrupt journal/sequence gap tests exist | Exact CI result associated with the tested SHA |
| G15 failure injection (T27) | Contract §10 | Scenario specified | Recorded deterministic failure-injection result for connection loss, duplicate response and stale data |
| G16 Demo soak | Contract §10 | Acceptance requirement specified | Approved run window, per-order status/cleanup/reconciliation records and incident summary; do not perform a real order merely to close this evidence gap |

## Safety disposition

- Phase B remains **LOCKED**.
- `IS_DEMO` and read-only checks are not substitutes for Phase A acceptance.
- No live trading, no order-placement test, and no Emergency Flatten action is authorized by this audit.
- Do not mark G10–G16 PASS or Phase 3 FROZEN from a green generic CI run.
- Preserve `UNVERIFIED_READ_ONLY`, `NO_DATA`, and `DOC_ONLY` statuses unless the specific claim is supported by its required evidence.
- Historical evidence artifacts are immutable for this audit; missing provenance is documented as a gap, not patched into old records.

## Next evidence-only work

1. Retrieve and verify the authentic workflow run/artifact for each of the three daily records; match date, run ID/attempt, commit SHA and artifact digest without changing the historical JSON.
2. Link every G10–G16 test ID to the exact test function, run, SHA, result and acceptance criterion. A filename or generic CI PASS is not sufficient.
3. Add missing deterministic mocked/failure-injection tests before considering any gate acceptance. Such tests must run offline and be incapable of reaching an exchange.
4. Inspect the downloadable read-only artifact bytes if the available connection permits; otherwise explicitly retain the result as not independently artifact-verified.
5. Run CI and associate the resulting PR head SHA and CI run URL with the review record.
6. Re-evaluate gate acceptance only after all required evidence and the required human approval are present.
