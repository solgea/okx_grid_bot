from dataclasses import dataclass
from typing import Protocol

from .task import TaskEnvelope


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    action: str
    reason: str


class PolicyEngine(Protocol):
    def evaluate(self, task: TaskEnvelope, action: str) -> PolicyDecision:
        ...
