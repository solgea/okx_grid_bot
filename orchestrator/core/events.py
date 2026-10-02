from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

@dataclass(frozen=True, slots=True)
class OrchestratorEvent:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    actor: str = ""
    payload: dict = field(default_factory=dict)
