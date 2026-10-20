# Phase Transition Approvals

## Current gate

- Phase A: **COMPLETE** (acceptance evidenced, see Evidence records)
- Phase B: **APPROVED** (G9 evidence recorded, see the approval record below)
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
| 3 consecutive UTC days | `artifacts/phase_a/2026-10-10.json` … `2026-10-20.json` (12 consecutive passing days) | PASS |
| Zero unexpected exchange order calls | every daily record reports `null_transport_only=true`, `unexpected_exchange_order_calls=0` | PASS |
| Zero unresolved incidents | every daily record reports `incidents=[]` | PASS |
| Section 11 OKX verification record | `artifacts/phase_a/okx-demo-assumptions-readonly-2026-10-12.json` | PASS |
| Phase-A test set | `docs/PHASE_A_TEST_EVIDENCE_MAP.md` | PASS |

The approval covers the **Demo** environment only. It does not enable mainnet
trading, withdrawals, account mutation, leverage or margin-mode changes, or
the emergency flatten path. `LIVE_TRADING_ENABLED`,
`LIVE_TRADING_AUTHORIZED`, `EMERGENCY_FLATTEN_ENABLED` and
`EMERGENCY_FLATTEN_AUTHORIZED` all remain `false`.

### G9 evidence — real OKX Demo order

G9 was executed against the OKX Demo environment on 2026-10-20 and produced
a real Demo `order_id`. The record is committed at
`artifacts/phase_a/g9-demo-order-2026-10-20.json`:

| Field | Value | Meaning |
|---|---|---|
| `order_id` | `4026561631765606401` | a real OKX Demo order id |
| `preflight` | `AUTHORIZED` | PreFlight authorized the order before submission |
| `status` | `canceled` | verified with `fetch_order` |
| `cleanup` | `CANCELED` | the cancellation was confirmed by the exchange |
| `filled` | `0.0` | the order never filled |
| `position_size` | `null` | no Demo position was left open |
| `verify_error` | `null` | the verification read succeeded |

This satisfies the contract's requirement that "a successful G9 run must
contain a real OKX Demo `order_id`" and that CI/test success alone is not
G9 PASS. The order was a limit order below market, it never filled, and the
cancellation was confirmed, so no open order and no position remain.

### Scope of the Phase-B promotion

The contract's Phase-B acceptance criteria additionally require
`en az N emirlik gerçek Demo çalıştırmasında her emir için status, cleanup ve
mutabakat kanıtı`. The G9 run above supplies that evidence for **one**
order. The count N is not fixed by the contract, so this promotion is
recorded on the strength of this single, fully verified order.

The following remain **unproven** and are explicitly carried into the first
controlled Phase-B run, as the Section 11 verification record already
flagged them:

- attached stop-loss support (`attachAlgoOrds`) and algo-order listing
- `reduceOnly` behaviour in net position mode
- duplicate `clOrdId` handling
- fee rates, fill fee fields and funding bills, which stay `NO_DATA` until
  an order actually fills

### How to reproduce the G9 evidence

```powershell
docker compose -f docker-compose.g9.yml build
docker compose -f docker-compose.g9.yml run --rm okx-grid-bot-g9
```

The run requires `IS_DEMO=true`, `DRY_RUN=false`, `G9_DEMO_CONFIRM=true` and
OKX Demo credentials in the local `.env`. It submits exactly one limit order,
verifies the real order state with `fetch_order`, and cancels the order if it
is still working. Credentials are never committed.

The 2026-10-20 run was made from a host whose network intercepted TLS to
`www.okx.com` and redirected it to an ISP warning page, which failed the
initial `load_markets()` call with `SSL: WRONG_VERSION_NUMBER`. No order was
submitted in that failed run. The evidence above is from a later, successful
run on the same day.

## Evidence records

Daily immutable evidence is written under `artifacts/phase_a/YYYY-MM-DD.json` by the scheduled Phase-A Shadow workflow. Missing days are not backfilled and cannot be marked PASS retrospectively.
