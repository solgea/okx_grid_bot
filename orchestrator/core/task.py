from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskEnvelope:
    """Immutable task contract submitted to the master orchestrator."""

    task_id: str
    type: str
    priority: str
    scope: str
    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    success_condition: str
