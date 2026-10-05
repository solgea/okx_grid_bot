from enum import Enum


class LifecycleState(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    ACKED = "ACKED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


_ALLOWED = {
    LifecycleState.NEW: {LifecycleState.SUBMITTED, LifecycleState.REJECTED},
    LifecycleState.SUBMITTED: {LifecycleState.ACKED, LifecycleState.UNKNOWN, LifecycleState.REJECTED},
    LifecycleState.ACKED: {LifecycleState.OPEN, LifecycleState.FILLED, LifecycleState.REJECTED},
    LifecycleState.OPEN: {LifecycleState.PARTIAL, LifecycleState.FILLED, LifecycleState.CANCELED, LifecycleState.UNKNOWN},
    LifecycleState.PARTIAL: {LifecycleState.FILLED, LifecycleState.CANCELED, LifecycleState.UNKNOWN},
}


class Lifecycle:
    def __init__(self) -> None:
        self.state = LifecycleState.NEW

    def transition(self, target: LifecycleState) -> None:
        if target not in _ALLOWED.get(self.state, set()):
            raise ValueError(f"invalid lifecycle transition: {self.state}->{target}")
        self.state = target
