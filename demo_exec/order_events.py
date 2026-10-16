"""Deterministic order-event processing for the Phase-A shadow executor.

No exchange/network dependency is permitted here. Phase A remains
NullTransport-only; real event-source wiring is a separately gated Phase-B
change and must not be inferred from these offline contracts.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .lifecycle import Lifecycle, LifecycleState


@dataclass(frozen=True)
class OrderEvent:
    event_id: str
    state: LifecycleState
    cumulative_filled: Decimal


@dataclass
class OrderEventProcessor:
    """Apply cumulative order updates monotonically and idempotently."""

    order_quantity: Decimal
    lifecycle: Lifecycle = field(default_factory=Lifecycle)
    cumulative_filled: Decimal = Decimal("0")
    _seen_event_ids: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self.order_quantity = self._decimal(self.order_quantity, "order_quantity")
        self.cumulative_filled = self._decimal(self.cumulative_filled, "cumulative_filled")
        if self.order_quantity <= 0:
            raise ValueError("order_quantity must be positive")
        if not Decimal("0") <= self.cumulative_filled <= self.order_quantity:
            raise ValueError("cumulative_filled is outside order quantity")

    @staticmethod
    def _decimal(value: Decimal, field_name: str) -> Decimal:
        try:
            parsed = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a finite decimal") from exc
        if not parsed.is_finite():
            raise ValueError(f"{field_name} must be a finite decimal")
        return parsed

    def mark_cancel_sent(self) -> None:
        """Record local cancel intent; does not issue an exchange cancellation."""
        if self.lifecycle.state not in {LifecycleState.OPEN, LifecycleState.PARTIAL}:
            raise ValueError(f"cancel not allowed in state {self.lifecycle.state}")
        self.lifecycle.transition(LifecycleState.CANCEL_SENT)

    def process(self, event: OrderEvent) -> bool:
        """Apply an event; False means duplicate or stale notification.

        A cancel confirmation is not proof that no fill event can arrive late.
        Lower cumulative quantities never roll back state or fill accounting.
        Invalid events are not added to the deduplication set.
        """
        if not event.event_id or not event.event_id.strip():
            raise ValueError("event_id is required")
        if event.event_id in self._seen_event_ids:
            return False
        if event.state not in {
            LifecycleState.ACKED,
            LifecycleState.OPEN,
            LifecycleState.PARTIAL,
            LifecycleState.FILLED,
            LifecycleState.CANCEL_CONFIRMED,
            LifecycleState.REJECTED,
            LifecycleState.UNKNOWN,
        }:
            raise ValueError(f"unsupported order event state: {event.state}")

        filled = self._decimal(event.cumulative_filled, "cumulative_filled")
        if filled < 0 or filled > self.order_quantity:
            raise ValueError("cumulative_filled is outside order quantity")
        if event.state is LifecycleState.PARTIAL and not (0 < filled < self.order_quantity):
            raise ValueError("PARTIAL requires 0 < cumulative_filled < order_quantity")
        if event.state is LifecycleState.FILLED and filled != self.order_quantity:
            raise ValueError("FILLED requires cumulative_filled == order_quantity")
        # Stale non-UNKNOWN notifications cannot regress fill accounting or
        # resolve an UNKNOWN lifecycle. Mark them seen so replay is idempotent.
        if filled < self.cumulative_filled and event.state is not LifecycleState.UNKNOWN:
            self._seen_event_ids.add(event.event_id)
            return False

        if event.state in {LifecycleState.ACKED, LifecycleState.OPEN, LifecycleState.REJECTED} and filled != self.cumulative_filled:
            raise ValueError(f"{event.state.value} cannot change cumulative fill")
        if event.state is LifecycleState.CANCEL_CONFIRMED:
            if filled != self.cumulative_filled:
                raise ValueError("cancel confirmation cannot change cumulative fill")
            if self.lifecycle.state not in {LifecycleState.CANCEL_SENT, LifecycleState.CANCEL_CONFIRMED}:
                raise ValueError("cancel confirmation received outside cancel flow")

        if self.lifecycle.state is LifecycleState.FILLED:
            self._seen_event_ids.add(event.event_id)
            return False

        allowed = {
            LifecycleState.ACKED: {LifecycleState.SUBMITTED},
            LifecycleState.OPEN: {LifecycleState.ACKED},
            LifecycleState.PARTIAL: {
                LifecycleState.OPEN, LifecycleState.PARTIAL,
                LifecycleState.CANCEL_SENT, LifecycleState.CANCEL_CONFIRMED,
            },
            LifecycleState.FILLED: {
                LifecycleState.ACKED, LifecycleState.OPEN, LifecycleState.PARTIAL,
                LifecycleState.CANCEL_SENT, LifecycleState.CANCEL_CONFIRMED,
            },
            LifecycleState.CANCEL_CONFIRMED: {
                LifecycleState.CANCEL_SENT, LifecycleState.CANCEL_CONFIRMED,
            },
            LifecycleState.REJECTED: {LifecycleState.SUBMITTED, LifecycleState.ACKED},
            # Unknown status may be reported after an accepted/open/partial order.
            # This is an order-event path, not an ordinary lifecycle transition.
            LifecycleState.UNKNOWN: {
                LifecycleState.SUBMITTED, LifecycleState.OPEN, LifecycleState.PARTIAL,
                LifecycleState.CANCEL_SENT, LifecycleState.CANCEL_CONFIRMED,
            },
        }
        current = self.lifecycle.state
        if current is LifecycleState.UNKNOWN:
            if event.state is LifecycleState.UNKNOWN:
                self._seen_event_ids.add(event.event_id)
                if filled > self.cumulative_filled:
                    self.cumulative_filled = filled
                    return True
                return False
            # Explicit resolution is restricted to authoritative order states;
            # cancellation confirmation alone cannot resolve ambiguous submit.
            self.lifecycle.resolve_unknown(event.state)
        elif current is not event.state and current not in allowed[event.state]:
            raise ValueError(f"event {event.state.value} invalid in state {current.value}")

        self._seen_event_ids.add(event.event_id)
        self.cumulative_filled = max(self.cumulative_filled, filled) if event.state is LifecycleState.UNKNOWN else filled
        if current is not LifecycleState.UNKNOWN and self.lifecycle.state is not event.state:
            self.lifecycle.transition(event.state)
        return True
