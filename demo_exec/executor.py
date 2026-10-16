from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from .intent import Intent
from .journal import Journal
from .lifecycle import Lifecycle, LifecycleState
from .order_events import OrderEvent, OrderEventProcessor
from .transport import NullTransport, Transport


# Phase A is a fixed-size shadow contract only. This is not an exchange order size.
# Phase B must source quantity from its validated order intent, never this constant.
SHADOW_ORDER_QUANTITY = Decimal("1")


@dataclass(frozen=True)
class SubmitResult:
    accepted: bool
    code: str
    state: str
    client_order_id: str


class DemoExecutor:
    """Single execution authority; Phase A is permanently NullTransport-only."""

    def __init__(self, transport: Transport, *, demo_phase: str = "A", enabled: bool = True, is_demo: bool = True, journal: Journal | None = None) -> None:
        if demo_phase != "A":
            raise ValueError("E_PHASE_LOCK: Phase A requires DEMO_PHASE=A")
        if not isinstance(transport, NullTransport):
            raise ValueError("E_PHASE_LOCK: Phase A requires NullTransport")
        self.transport = transport
        self.enabled = enabled
        self.is_demo = is_demo
        self.journal = journal
        self._seen: set[tuple[str, int]] = set()
        self._stopped = False
        self._order_events: dict[str, OrderEventProcessor] = {}
        if journal:
            for row in journal.read():
                if row.get("event") == "INTENT":
                    self._seen.add((str(row["agent_id"]), int(row["seq"])))
                elif row.get("event") in {"UNKNOWN", "ORDER_EVENT", "CANCEL_INTENT"}:
                    # Event state is not reconstructed from an incomplete journal.
                    # Stop on restart rather than guess at exchange/order reality.
                    self._stopped = True

    async def submit(self, intent: Intent) -> SubmitResult:
        cl_id = self._cl_id(intent)
        if not self.is_demo:
            return SubmitResult(False, "E_NOT_DEMO", LifecycleState.NEW.value, cl_id)
        if not self.enabled:
            return SubmitResult(False, "E_DISABLED", LifecycleState.NEW.value, cl_id)
        key = (intent.agent_id, intent.seq)
        if key in self._seen:
            return SubmitResult(False, "E_JOURNAL", LifecycleState.NEW.value, cl_id)
        if self._stopped:
            return SubmitResult(False, "E_AGENT_STATE", LifecycleState.UNKNOWN.value, cl_id)
        if intent.seq < 1:
            return SubmitResult(False, "E_LIMIT", LifecycleState.NEW.value, cl_id)
        if self.journal:
            try:
                self.journal.append({"event": "INTENT", "agent_id": intent.agent_id, "seq": intent.seq, "symbol": intent.symbol})
            except OSError:
                return SubmitResult(False, "E_JOURNAL", LifecycleState.NEW.value, cl_id)
        self._seen.add(key)
        try:
            result = await self.transport.place(intent)
        except (TimeoutError, ConnectionError):
            self._stopped = True
            # Preserve a correlation target for authoritative late events. The
            # executor remains stopped for new submissions, but a known order ID
            # may still resolve UNKNOWN to actual exchange-reported state.
            lifecycle = Lifecycle()
            lifecycle.transition(LifecycleState.SUBMITTED)
            lifecycle.transition(LifecycleState.UNKNOWN)
            self._order_events[cl_id] = OrderEventProcessor(
                order_quantity=SHADOW_ORDER_QUANTITY, lifecycle=lifecycle
            )
            if self.journal:
                try:
                    self.journal.append({"event": "UNKNOWN", "agent_id": intent.agent_id, "seq": intent.seq})
                except OSError:
                    pass
            return SubmitResult(False, "E_TRANSPORT", LifecycleState.UNKNOWN.value, cl_id)
        if result.client_order_id != cl_id:
            self._stopped = True
            if self.journal:
                try:
                    self.journal.append({"event": "UNKNOWN", "agent_id": intent.agent_id, "seq": intent.seq, "reason": "E_CLIENT_ORDER_ID_MISMATCH"})
                except OSError:
                    pass
            return SubmitResult(False, "E_CLIENT_ORDER_ID_MISMATCH", LifecycleState.UNKNOWN.value, cl_id)

        lifecycle = Lifecycle()
        lifecycle.transition(LifecycleState.SUBMITTED)
        # Phase A NullTransport has a fixed one-unit shadow contract. This is
        # not an exchange order quantity and cannot be reused for Phase B.
        self._order_events[cl_id] = OrderEventProcessor(
            order_quantity=Decimal("1"), lifecycle=lifecycle
        )
        return SubmitResult(True, "SHADOW", LifecycleState.SUBMITTED.value, cl_id)

    def mark_cancel_sent(self, client_order_id: str) -> None:
        """Record a local cancel intent for the shadow lifecycle; sends no cancel."""
        if self._stopped:
            raise RuntimeError("E_AGENT_STATE: executor is stopped")
        processor = self._order_events.get(client_order_id)
        if processor is None:
            self._stop_for_unknown_order(client_order_id)
        try:
            processor.mark_cancel_sent()
            if self.journal:
                self.journal.append({"event": "CANCEL_INTENT", "client_order_id": client_order_id})
        except (ValueError, OSError):
            self._stopped = True
            raise

    def handle_order_event(self, client_order_id: str, event: OrderEvent) -> bool:
        """Route a validated event through the executor's tracked shadow order.

        This is an offline event-ingress seam only. No exchange watcher or
        Phase-B transport is enabled by this method. Known order events remain
        admissible after the executor stops new submissions, so late fill
        evidence is not discarded.
        """
        processor = self._order_events.get(client_order_id)
        if processor is None:
            self._stop_for_unknown_order(client_order_id)
        try:
            accepted = processor.process(event)
            if event.state is LifecycleState.UNKNOWN:
                self._stopped = True
            if accepted and self.journal:
                self.journal.append({
                    "event": "ORDER_EVENT",
                    "client_order_id": client_order_id,
                    "event_id": event.event_id,
                    "state": event.state.value,
                    "cumulative_filled": str(event.cumulative_filled),
                })
            return accepted
        except (ValueError, OSError):
            self._stopped = True
            raise

    def _stop_for_unknown_order(self, client_order_id: str) -> None:
        self._stopped = True
        if self.journal:
            try:
                self.journal.append({
                    "event": "UNKNOWN",
                    "reason": "E_UNKNOWN_CLIENT_ORDER_ID",
                    "client_order_id": client_order_id,
                })
            except OSError:
                pass
        raise ValueError("E_UNKNOWN_CLIENT_ORDER_ID")

    @staticmethod
    def _cl_id(intent: Intent) -> str:
        value = f"g{intent.agent_id}{intent.seq}"
        if value.isascii() and value.isalnum() and len(value) <= 32:
            return value
        digest = sha256(f"{intent.agent_id}:{intent.seq}".encode("utf-8")).hexdigest()
        normalized = f"g{digest[:31]}"
        if not normalized.isascii() or not normalized.isalnum() or len(normalized) > 32:
            raise ValueError("failed to normalize clOrdId")
        return normalized
