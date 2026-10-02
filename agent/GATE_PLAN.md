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

## G10 — Order Lifecycle
Validate acknowledgement, open/fill/cancel/reject lifecycle.

## G11 — OrderSync Live-Demo
Validate reconciliation against real Demo open orders.

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
