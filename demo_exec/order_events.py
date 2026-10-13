"""Offline order-event processor for the Phase-A execution contract.

This component has no exchange/network dependency and is not wired to a live
transport. Production adapters must call it only after identity and schema
validation; Phase A remains NullTransport-only.
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

    def process(self, event: OrderEvent) -> bool:
        """Apply an event; return False for duplicate or stale notifications.

        A lower cumulative fill is stale and ignored. It never rolls state or
        quantity backward. A cancel confirmation is not proof of zero fills:
        later larger cumulative fill notifications remain authoritative.
        """
        if not event.event_id or not event.event_id.strip():
            raise ValueError("event_id is required")
        if event.event_id in self._seen_event_ids:
            return False
        if event.state not in {
            LifecycleState.PARTIAL,
            LifecycleState.FILLED,
            LifecycleState.CANCEL_CONFIRMED,
        }:
            raise ValueError(f"unsupported order event state: {event.state}")

        filled = self._decimal(event.cumulative_filled, "cumulative_filled")
        if filled < 0 or filled > self.order_quantity:
            raise ValueError("cumulative_filled is outside order quantity")
        if event.state is LifecycleState.PARTIAL and not (0 < filled < self.order_quantity):
            raise ValueError("PARTIAL requires 0 < cumulative_filled < order_quantity")
        if event.state is LifecycleState.FILLED and filled != self.order_quantity:
            raise ValueError("FILLED requires cumulative_filled == order_quantity")

        self._seen_event_ids.add(event.event_id)
        if filled < self.cumulative_filled:
            return False

        if event.state is LifecycleState.CANCEL_CONFIRMED:
            if filled != self.cumulative_filled:
                raise ValueError("cancel confirmation cannot change cumulative fill")
            if self.lifecycle.state is LifecycleState.CANCEL_SENT:
                self.lifecycle.transition(LifecycleState.CANCEL_CONFIRMED)
            elif self.lifecycle.state is not LifecycleState.CANCEL_CONFIRMED:
                raise ValueError("cancel confirmation received outside cancel flow")
            return True

        # A repeated PARTIAL state may update cumulative quantity without a
        # lifecycle transition; FILLED remains the terminal execution state.
        if self.lifecycle.state is LifecycleState.FILLED:
            return False
        if event.state is LifecycleState.PARTIAL:
            if self.lifecycle.state not in {
                LifecycleState.OPEN,
                LifecycleState.PARTIAL,
                LifecycleState.CANCEL_SENT,
                LifecycleState.CANCEL_CONFIRMED,
            }:
                raise ValueError(f"partial fill received in state {self.lifecycle.state}")
        elif event.state is LifecycleState.FILLED:
            if self.lifecycle.state not in {
                LifecycleState.ACKED,
                LifecycleState.OPEN,
                LifecycleState.PARTIAL,
                LifecycleState.CANCEL_SENT,
                LifecycleState.CANCEL_CONFIRMED,
            }:
                raise ValueError(f"full fill received in state {self.lifecycle.state}")

        self.cumulative_filled = filled
        if self.lifecycle.state is not event.state:
            self.lifecycle.transition(event.state)
        return True
