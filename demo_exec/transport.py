from dataclasses import dataclass
from typing import Protocol

from .intent import Intent


class Transport(Protocol):
    async def place(self, intent: Intent) -> "TransportResult":
        ...


@dataclass(frozen=True)
class TransportResult:
    status: str
    client_order_id: str


class NullTransport:
    """Phase-A transport. It records an attempted placement but never touches an exchange."""

    def __init__(self) -> None:
        self.place_calls = 0

    async def place(self, intent: Intent) -> TransportResult:
        self.place_calls += 1
        return TransportResult("SHADOW_NOT_SENT", f"g{intent.agent_id}{intent.seq}")
