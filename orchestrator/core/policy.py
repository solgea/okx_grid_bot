from dataclasses import dataclass
from typing import Protocol

from .task import TaskEnvelope

@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    action: str
    reason: str

class PolicyEngine(Protocol):
    def evaluate(self, task: TaskEnvelope, action: str) -> PolicyDecision: ...

class DefaultPolicyEngine:
    RESTRICTED_ACTIONS = frozenset({"live_order","live_withdrawal","live_account_mutation","production_deploy","policy_change","merge_pr"})
    INTERNAL_ACTIONS = frozenset({"review"})

    def evaluate(self, task: TaskEnvelope, action: str) -> PolicyDecision:
        if action in self.RESTRICTED_ACTIONS:
            return PolicyDecision(False, action, "restricted action denied by default")
        if action in self.INTERNAL_ACTIONS:
            return PolicyDecision(True, action, "internal control-plane action allowed")
        if action not in task.allowed_actions:
            return PolicyDecision(False, action, "action is not allowed by task envelope")
        if action in task.forbidden_actions:
            return PolicyDecision(False, action, "action is forbidden by task envelope")
        return PolicyDecision(True, action, "allowed by task and global policy")
