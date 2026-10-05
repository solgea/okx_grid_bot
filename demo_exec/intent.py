from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Intent:
    agent_id: str
    symbol: str
    side: str
    reason: str
    seq: int
    ts: str

    @classmethod
    def create(cls, agent_id: str, symbol: str, side: str, reason: str, seq: int) -> "Intent":
        if not agent_id or not symbol or side not in {"buy", "sell"}:
            raise ValueError("invalid intent")
        if seq < 1:
            raise ValueError("seq must be positive")
        return cls(agent_id, symbol, side, reason, seq, datetime.now(timezone.utc).isoformat())
