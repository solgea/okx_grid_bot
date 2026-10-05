from dataclasses import dataclass

from .intent import Intent
from .lifecycle import LifecycleState
from .transport import NullTransport, Transport


@dataclass(frozen=True)
class SubmitResult:
    accepted: bool
    code: str
    state: str
    client_order_id: str


class DemoExecutor:
    """Single execution authority for Phase A.

    Phase A is deliberately limited to NullTransport. Any other transport is rejected.
    """

    def __init__(self, transport: Transport, *, demo_phase: str = "A", enabled: bool = True) -> None:
        if demo_phase != "A":
            raise ValueError("E_PHASE_LOCK: Phase A requires DEMO_PHASE=A")
        if not isinstance(transport, NullTransport):
            raise ValueError("E_PHASE_LOCK: Phase A requires NullTransport")
        self.transport = transport
        self.enabled = enabled
        self._seen: set[tuple[str, int]] = set()

    async def submit(self, intent: Intent) -> SubmitResult:
        if not self.enabled:
            return SubmitResult(False, "E_DISABLED", LifecycleState.NEW.value, self._cl_id(intent))
        key = (intent.agent_id, intent.seq)
        if key in self._seen:
            return SubmitResult(False, "E_JOURNAL", LifecycleState.NEW.value, self._cl_id(intent))
        if intent.seq < 1:
            return SubmitResult(False, "E_LIMIT", LifecycleState.NEW.value, self._cl_id(intent))

        self._seen.add(key)
        result = await self.transport.place(intent)
        return SubmitResult(True, "SHADOW", LifecycleState.SUBMITTED.value, result.client_order_id)

    @staticmethod
    def _cl_id(intent: Intent) -> str:
        value = f"g{intent.agent_id}{intent.seq}"
        if not value.isalnum() or len(value) > 32:
            raise ValueError("invalid clOrdId")
        return value
