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
        return await self.place_spec(
            symbol=intent.symbol,
            side=intent.side,
            amount=1,
            price=None,
            params={"clientOrderId": f"g{intent.agent_id}{intent.seq}"},
        )

    async def place_spec(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        price: float | None,
        params: dict[str, Any],
    ) -> TransportResult:
        self.place_calls += 1
        return TransportResult("SHADOW_NOT_SENT", str(params.get("clientOrderId") or ""))


class OkxDemoTransport:
    """Controlled OKX transport. Instantiation is Phase-B/demo gated."""

    def __init__(self, exchange: Any, *, demo_phase: str, is_demo: bool) -> None:
        if demo_phase == "A":
            raise RuntimeError("E_PHASE_LOCK")
        if not is_demo:
            raise RuntimeError("E_NOT_DEMO")
        self.exchange = exchange

    async def place(self, intent: Intent) -> TransportResult:
        return await self.place_spec(
            symbol=intent.symbol,
            side=intent.side,
            amount=1,
            price=None,
            params={"clientOrderId": f"g{intent.agent_id}{intent.seq}"},
        )

    async def place_spec(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        price: float | None,
        params: dict[str, Any],
    ) -> TransportResult:
        order = await self.exchange.create_order(
            symbol=symbol,
            type="limit",
            side=side,
            amount=amount,
            price=price,
            params=params,
        )
        return TransportResult(
            str(order.get("status") or "ACKED"),
            str(order.get("id") or ""),
        )
