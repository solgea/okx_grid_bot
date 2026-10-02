from dataclasses import dataclass
from orchestrator.core.task import TaskEnvelope

@dataclass(frozen=True, slots=True)
class RuntimeTask:
    envelope: TaskEnvelope

    @classmethod
    def from_dict(cls, payload: dict) -> "RuntimeTask":
        return cls(TaskEnvelope(
            task_id=str(payload["task_id"]),
            type=str(payload["type"]),
            priority=str(payload["priority"]),
            scope=str(payload["scope"]),
            allowed_actions=tuple(payload["allowed_actions"]),
            forbidden_actions=tuple(payload["forbidden_actions"]),
            success_condition=str(payload["success_condition"]),
        ))
