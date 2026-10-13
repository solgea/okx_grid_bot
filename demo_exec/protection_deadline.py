"""Offline protection-deadline contract for Phase-A shadow validation.

This module only classifies whether protection was confirmed in time. It never
places orders, closes positions, or calls an exchange. A real emergency
reduce-only close remains separately gated and is deliberately not implemented
here.
"""
from dataclasses import dataclass
from enum import Enum
import math


PROTECT_DEADLINE_SEC = 5.0


class ProtectionStatus(str, Enum):
    WAITING_FOR_POSITION = "WAITING_FOR_POSITION"
    UNPROTECTED = "UNPROTECTED"
    PROTECTED = "PROTECTED"
    EXPIRED = "EXPIRED"


@dataclass
class ProtectionDeadline:
    """Track the five-second window from first position detection.

    now values must come from one monotonic clock domain. Callers inject
    timestamps so tests stay deterministic and require no sleeps.
    """

    deadline_sec: float = PROTECT_DEADLINE_SEC
    detected_at: float | None = None
    status: ProtectionStatus = ProtectionStatus.WAITING_FOR_POSITION

    def __post_init__(self) -> None:
        self.deadline_sec = self._finite(self.deadline_sec, "deadline_sec")
        if self.deadline_sec <= 0:
            raise ValueError("deadline_sec must be positive")

    @staticmethod
    def _finite(value: float, field: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{field} must be finite") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"{field} must be finite")
        return parsed

    @property
    def emergency_action_required(self) -> bool:
        """Signal required escalation; this object performs no close action."""
        return self.status is ProtectionStatus.EXPIRED

    def position_detected(self, now: float) -> bool:
        """Start the clock once; duplicate detections cannot reset the deadline."""
        timestamp = self._finite(now, "now")
        if self.detected_at is not None:
            return False
        self.detected_at = timestamp
        self.status = ProtectionStatus.UNPROTECTED
        return True

    def check(self, now: float) -> ProtectionStatus:
        """Expire only after the deadline; exactly-at-deadline is still in time."""
        timestamp = self._finite(now, "now")
        if self.detected_at is None or self.status in {
            ProtectionStatus.PROTECTED,
            ProtectionStatus.EXPIRED,
        }:
            return self.status
        elapsed = timestamp - self.detected_at
        if elapsed < 0 or elapsed > self.deadline_sec:
            self.status = ProtectionStatus.EXPIRED
        return self.status

    def confirm_protection(self, now: float) -> bool:
        """Accept protection only if confirmed no later than the deadline."""
        timestamp = self._finite(now, "now")
        if self.detected_at is None:
            self.status = ProtectionStatus.EXPIRED
            return False
        self.check(timestamp)
        if self.status is ProtectionStatus.EXPIRED:
            return False
        self.status = ProtectionStatus.PROTECTED
        return True
