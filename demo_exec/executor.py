from dataclasses import dataclass
from hashlib import sha256

from .intent import Intent
from .journal import Journal
from .lifecycle import LifecycleState
from .transport import NullTransport, Transport


@dataclass(frozen=True)
class SubmitResult:
    accepted: bool
    code: str
    state: str
    client_order_id: str


class DemoExecutor:
    """Single execution authority; Phase A is permanently NullTransport-only."""
    def __init__(self, transport: Transport, *, demo_phase: str = "A", enabled: bool = True, journal: Journal | None = None) -> None:
        if demo_phase != "A":
            raise ValueError("E_PHASE_LOCK: Phase A requires DEMO_PHASE=A")
        if not isinstance(transport, NullTransport):
            raise ValueError("E_PHASE_LOCK: Phase A requires NullTransport")
        self.transport = transport
        self.enabled = enabled
        self.journal = journal
        self._seen: set[tuple[str, int]] = set()
        if journal:
            for row in journal.read():
                if row.get("event") == "INTENT":
                    self._seen.add((str(row["agent_id"]), int(row["seq"])))

    async def submit(self, intent: Intent) -> SubmitResult:
        cl_id = self._cl_id(intent)
        if not self.enabled:
            return SubmitResult(False, "E_DISABLED", LifecycleState.NEW.value, cl_id)
        key = (intent.agent_id, intent.seq)
        if key in self._seen:
            return SubmitResult(False, "E_JOURNAL", LifecycleState.NEW.value, cl_id)
        if intent.seq < 1:
            return SubmitResult(False, "E_LIMIT", LifecycleState.NEW.value, cl_id)
        if self.journal:
            try:
                self.journal.append({"event":"INTENT","agent_id":intent.agent_id,"seq":intent.seq,"symbol":intent.symbol})
            except OSError:
                return SubmitResult(False, "E_JOURNAL", LifecycleState.NEW.value, cl_id)
        self._seen.add(key)
        try:
            result = await self.transport.place(intent)
        except TimeoutError:
            if self.journal:
                self.journal.append({"event":"UNKNOWN","agent_id":intent.agent_id,"seq":intent.seq})
            return SubmitResult(False, "E_TRANSPORT", LifecycleState.UNKNOWN.value, cl_id)
        return SubmitResult(True, "SHADOW", LifecycleState.SUBMITTED.value, result.client_order_id)

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
