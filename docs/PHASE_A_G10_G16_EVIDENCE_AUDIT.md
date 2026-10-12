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

## Contract-to-evidence mapping

| Requirement | Current evidence source | Audit status | What remains unproven |
|---|---|---|---|
| Phase A evidence provenance and count consistency | `scripts/record_phase_a_evidence.py`, `tests/test_demo_phase_a_shadow.py`, `.github/workflows/phase-a-evidence.yml` | Code/test coverage present; baseline CI passed | Three distinct consecutive daily workflow records and cross-day continuity |
| OKX assumptions check is read-only | `scripts/okx_demo_assumptions_check.py`, `tests/test_okx_assumptions_check.py`, `.github/workflows/okx-demo-assumptions-readonly.yml` | Read-only safeguards and mocked tests present; baseline CI includes read-only Docker smoke | Real secret-backed workflow artifact/result must be inspected separately; no mutating request may be used to prove assumptions |
| G8.6 preflight authorization | `agent/GATE_PLAN.md` and existing preflight implementation/tests | Gate requirement documented | Current CI success alone does not prove every G8.6 negative path unless linked to specific test output |
| G10 order lifecycle (T09–T13) | `docs/DEMO_EXECUTION_CONTRACT.md` §4, §9 | Contract/test scenarios specified | Controlled evidence for acknowledgement, timeout/UNKNOWN, cancel/fill race, partial fill and duplicate/delayed responses |
| G11 reconciliation (T14–T15) | `docs/DEMO_EXECUTION_CONTRACT.md` §8–10 | Contract/test scenarios specified | Evidence of mismatch fail-stop and untouched untagged orders |
| G12 position integrity | `docs/DEMO_EXECUTION_CONTRACT.md` §5, §10 | Contract requirement specified | Explicit position-state/size test evidence |
| G13 risk / kill switch (T19–T22) | `docs/DEMO_EXECUTION_CONTRACT.md` §6, §9–10 | Contract/test scenarios specified | Explicit threshold, hard-stop, cleanup and kill-switch test evidence |
| G14 restart recovery (T25–T26) | `docs/DEMO_EXECUTION_CONTRACT.md` §8–10 | Contract/test scenarios specified | Restart/replay evidence for paused recovery, corrupt journal and sequence gap |
| G15 failure injection (T27) | `docs/DEMO_EXECUTION_CONTRACT.md` §10 | Contract scenario specified | Recorded failure-injection test evidence |
| G16 Demo soak | `docs/DEMO_EXECUTION_CONTRACT.md` §10 | Acceptance requirement specified | Defined run window, per-order status/cleanup/reconciliation evidence and incident summary |

## Safety disposition

- Phase B remains **LOCKED**.
- `IS_DEMO` and read-only checks are not substitutes for Phase A acceptance.
- No live trading, no order-placement test, and no Emergency Flatten action is authorized by this audit.
- Do not mark G10–G16 PASS or Phase 3 FROZEN from a green generic CI run.
- Any unknown/unproven behavior must remain explicitly unverified until the required evidence exists.

## Next evidence-only work

1. Link each existing test to the contract test IDs it actually covers; do not infer coverage from filenames.
2. Inspect the Phase A workflow's separate daily artifacts and verify three distinct consecutive UTC dates, provenance, count consistency, and zero unresolved incidents.
3. For any missing G10–G16 test, add a deterministic mocked/failure-injection test first. Keep all such tests offline and incapable of reaching an exchange.
4. Run CI and associate the resulting PR head SHA and CI run URL with the review record.
5. Re-evaluate the gate only after the complete acceptance criteria and required human approval are present.
