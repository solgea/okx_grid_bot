from dataclasses import dataclass
from typing import Protocol, Any

from .intent import Intent


class Transport(Protocol):
    async def place(self, intent: Intent) -> "TransportResult": ...


@dataclass(frozen=True)
class TransportResult:
    status: str
    client_order_id: str


class NullTransport:
    """Phase-A transport. Records a shadow placement and never touches an exchange."""
    def __init__(self) -> None:
        self.place_calls = 0

    async def place(self, intent: Intent) -> TransportResult:
        self.place_calls += 1
        return TransportResult("SHADOW_NOT_SENT", f"g{intent.agent_id}{intent.seq}")


class OkxDemoTransport:
    """The sole owner of Demo create_order. Never constructible in Phase A or live mode."""
    def __init__(self, exchange: Any, *, demo_phase: str = "B", is_demo: bool = True) -> None:
        if demo_phase == "A":
            raise ValueError("E_PHASE_LOCK: real transport forbidden in Phase A")
        if not is_demo:
            raise ValueError("E_NOT_DEMO: Demo transport requires IS_DEMO=true")
        self.exchange = exchange

    async def place(self, intent: Intent) -> TransportResult:
        order = await self.exchange.create_order(
            symbol=intent.symbol,
            type="limit",
            side=intent.side,
            amount=1,
            price=None,
            params={"clientOrderId": f"g{intent.agent_id}{intent.seq}"},
        )
        return TransportResult(str(order.get("status") or "ACKED"), str(order["id"]))
