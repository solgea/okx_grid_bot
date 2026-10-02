from orchestrator.core.events import OrchestratorEvent

class AuditLog:
    def __init__(self):
        self._events = {}
    def append(self, event: OrchestratorEvent) -> None:
        if event.event_id in self._events:
            raise ValueError(f"duplicate event_id: {event.event_id}")
        self._events[event.event_id] = event
    def events(self, task_id: str):
        return tuple(e for e in self._events.values() if e.task_id == task_id)
