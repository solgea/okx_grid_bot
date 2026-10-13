# Delayed-fill event ingress design (Phase A)

## Purpose

Exercise the delayed-fill safety contract through the same event-ingress method owned by `DemoExecutor`, instead of testing only raw lifecycle transitions. This is a deterministic offline contract and does not establish real OKX event delivery semantics.

## Flow

1. `DemoExecutor` remains gated to `demo_phase="A"` and `NullTransport` only.
2. A successful shadow submit registers an event processor keyed by the deterministic client order ID. The quantity of `1` is the NullTransport fixture quantity only; it is not an exchange order size.
3. A validated ACKED/OPEN event advances the shadow lifecycle.
4. `mark_cancel_sent` records local cancel intent only; it never calls an exchange cancellation.
5. CANCEL_CONFIRMED is recorded with the current cumulative fill quantity.
6. A later PARTIAL/FILLED event is accepted only when cumulative quantity is monotonic and within the tracked quantity. Duplicate event IDs are ignored. Lower cumulative quantities are ignored without state regression.
7. An unknown client order ID, invalid state transition, or journal write failure stops the executor (fail-closed). On restart, event/cancel journal entries stop the executor because the current journal format does not reconstruct full order-event state.

## Explicit non-goals and gates

- No event watcher/websocket/private exchange event source is implemented or enabled.
- No OKX requests, order placements, cancellations, account mutations, or Emergency Flatten are performed by these tests.
- This code does not authorize Phase B and does not prove production event-path or real exchange cancel/fill behavior.
- Before Phase B can be considered, a separately reviewed adapter must validate exchange event schema and order identity, source authoritative cumulative fills, persist/recover event state, reconcile exchange snapshots, and remain behind existing G8.6/G10-G16 gates. Phase B remains LOCKED until those independent gates have evidence.
- Historical Phase A evidence JSON files are immutable and are not changed by this work.
