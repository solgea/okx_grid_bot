# Phase Transition Approvals

## Current gate

- Phase A: **COMPLETE** (acceptance evidenced, see Evidence records)
- Phase B: **APPROVED, PENDING G9 EVIDENCE** (see the approval record below)
- Live trading: **DISABLED**
- Emergency flatten: **DISABLED**

## Human authorization

The project owner has granted authority to execute controlled project steps without repeated approval prompts.

This authorization does **not** waive Demo Execution Contract gates. In particular, Phase B remains blocked until the contract's Phase-A acceptance criteria are objectively evidenced, including 3 consecutive UTC days, required tests, zero unexpected exchange order calls, zero unresolved incidents, and the required OKX verification record.

## Approval record — Phase A → Phase B

- Date: 2026-10-20
- Approved by: the project owner (repository owner)
- Scope: the Phase-A → Phase-B transition defined in
  [docs/DEMO_EXECUTION_CONTRACT.md](../docs/DEMO_EXECUTION_CONTRACT.md) section 10.

### Rationale

The Phase-A acceptance criteria are objectively satisfied in the repository:

| Criterion | Evidence | Result |
|---|---|---|
| 3 consecutive UTC days | `artifacts/phase_a/2026-10-10.json` … `2026-10-19.json` (10 consecutive passing days) | PASS |
| Zero unexpected exchange order calls | every daily record reports `null_transport_only=true`, `unexpected_exchange_order_calls=0` | PASS |
| Zero unresolved incidents | every daily record reports `incidents=[]` | PASS |
| Section 11 OKX verification record | `artifacts/phase_a/okx-demo-assumptions-readonly-2026-10-12.json` | PASS |
| Phase-A test set | `docs/PHASE_A_TEST_EVIDENCE_MAP.md` | PASS |

The approval covers the **Demo** environment only. It does not enable mainnet
trading, withdrawals, account mutation, leverage or margin-mode changes, or
the emergency flatten path. `LIVE_TRADING_ENABLED`,
`LIVE_TRADING_AUTHORIZED`, `EMERGENCY_FLATTEN_ENABLED` and
`EMERGENCY_FLATTEN_AUTHORIZED` all remain `false`.

### Outstanding prerequisite before the first Phase-B run

The contract's Phase-B acceptance criteria additionally require
`en az N emirlik gerçek Demo çalıştırmasında her emir için status, cleanup ve
mutabakat kanıtı`. **That evidence does not exist yet:** G9 has never been
run against the OKX Demo environment, so the repository holds no real Demo
`order_id`, no `status`/`cleanup` record and no reconciliation evidence for a
real Demo order.

`docs/G9_DEMO_EXECUTION.md` is explicit that "CI/test success alone is not
G9 PASS" and that a successful G9 run must contain a real OKX Demo
`order_id`.

Therefore this approval records the **human decision** to enter Phase B. The
first controlled Phase-B run is still gated on the G9 run producing that
evidence. The Phase-B promotion is not complete until that evidence is
committed here.

### How to produce the missing evidence

```powershell
docker compose -f docker-compose.g9.yml build
docker compose -f docker-compose.g9.yml run --rm okx-grid-bot-g9
```

The run requires `IS_DEMO=true`, `DRY_RUN=false`, `G9_DEMO_CONFIRM=true` and
OKX Demo credentials in the local `.env`. It submits exactly one limit order,
verifies the real order state with `fetch_order`, and cancels the order if it
is still working. Credentials are never committed.

## Evidence records

Daily immutable evidence is written under `artifacts/phase_a/YYYY-MM-DD.json` by the scheduled Phase-A Shadow workflow. Missing days are not backfilled and cannot be marked PASS retrospectively.
