# Phase 3 Gate Plan — Agent-Controlled

## G8 — Execution Preflight
- G8.1 instrument metadata, live status, tick/lot/min size, contract value, instrument identity
- G8.2 price/quantity validity and alignment, max position size
- G8.3 leverage, account leverage, required margin
- G8.4 market availability, positive last, valid timestamp, freshness
- G8.5 kill switch, trading halt, position limit, friction/risk validation
- G8.6 PreFlight != AUTHORIZED => no exchange order

## G9 — Demo Order Placement
Validate only after G8 is complete.

**Status: PASS (2026-10-20).** A real OKX Demo order was authorized by
PreFlight, never filled, and was cancelled with the cancellation confirmed
by the exchange. Evidence:
`artifacts/phase_a/g9-demo-order-2026-10-20.json`.

## G10 — Order Lifecycle
Validate acknowledgement, open/fill/cancel/reject lifecycle.

## G11 — OrderSync Live-Demo
Validate reconciliation against real Demo open orders.

**Status: partially covered.** The reconciliation contract is covered by the
T11 tests in `tests/test_demo_contract_gates.py` (managed orders match,
missing or extra orders stop without repair, foreign orders are ignored).
What is **not** yet covered is reconciliation against *real* Demo open
orders, which needs a Demo run that leaves an order working on purpose.

## G12 — Position Integrity
Validate position state and sizing.

## G13 — Risk/Kill Switch
Validate runtime risk controls under Demo.

## G14 — Restart Recovery
Validate safe recovery after restart.

## G15 — Failure Injection
Validate deliberate failure paths.

## G16 — Demo Soak
Validate sustained Demo operation.

## G17 — Phase 3 Freeze
Freeze only with explicit evidence for all prior gates.

A passing CI suite does not by itself mark a gate complete. Inspect implementation evidence and choose the next single missing control.

## Known contract gaps

These are contract requirements that the code does not yet enforce. They are
recorded here so they are not mistaken for covered gates.

| Contract ID | Requirement | Current state |
|---|---|---|
| D1 / T18 | one active Demo agent per symbol | **Not enforced.** `DemoExecutor.submit` does not track which agent holds which symbol, so a second agent on the same symbol is not refused with `E_LIMIT`. The `E_LIMIT` code exists but is only raised for `seq < 1`. |
| D1 | at most 1 contract position and order | **Not enforced** in the executor. The manual Demo panel caps its own order at one contract, but the executor does not check position or open-order size. |
| D2 | entry limit order, TTL 10 sn, `reduceOnly=false`; exit `reduceOnly=true` | **Not enforced** by the executor. The Phase-A shadow path does not open real orders, so no TTL or reduce-only behaviour is implemented yet. |
| D3 / D6 | daily loss limit %2 and hard stop %3 | **Not enforced.** `demo_exec/risk.py` does not exist. The bot's own `RiskManager` implements separate drawdown and daily-loss limits for the grid path, but the contract's per-agent daily equity snapshot and the %3 hard stop are not implemented. |
| D7 | entry price bound 0,002 and `MAX_SPREAD_PCT` | **Not enforced.** `MAX_SPREAD_PCT` is still an open value in the contract's section 12. |
| I5 / I7 | protective stop loss within `PROTECT_DEADLINE_SEC` | **Partially covered.** `demo_exec/protection_deadline.py` classifies the deadline offline, but no protective order is ever sent. |
