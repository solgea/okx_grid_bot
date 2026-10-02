from orchestrator.core.policy import DefaultPolicyEngine
from .models import RuntimeTask

_REQUIRED = ("task_id", "type", "priority", "scope", "allowed_actions", "forbidden_actions", "success_condition")

class TaskIntake:
    def __init__(self, policy=None):
        self.policy = policy or DefaultPolicyEngine()

    def validate(self, payload: dict):
        if not isinstance(payload, dict):
            raise ValueError("task payload must be an object")
        missing = [key for key in _REQUIRED if key not in payload]
        if missing:
            raise ValueError(f"missing task fields: {', '.join(missing)}")
        if not isinstance(payload["allowed_actions"], list) or not isinstance(payload["forbidden_actions"], list):
            raise ValueError("allowed_actions and forbidden_actions must be arrays")
        task = RuntimeTask.from_dict(payload).envelope
        for action in task.allowed_actions:
            decision = self.policy.evaluate(task, action)
            if not decision.allowed and action in DefaultPolicyEngine.RESTRICTED_ACTIONS:
                raise ValueError(f"restricted action requested: {action}")
        return task
