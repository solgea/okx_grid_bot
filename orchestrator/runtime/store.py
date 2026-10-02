import json
from dataclasses import asdict
from pathlib import Path
from orchestrator.core.events import OrchestratorEvent
from orchestrator.core.state import TaskState
from orchestrator.memory.task_store import TaskRecord
from orchestrator.core.task import TaskEnvelope

class _PersistentAudit:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, event: OrchestratorEvent):
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True, default=str) + "\n")

    def events(self, task_id: str):
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            data = json.loads(line)
            if data["task_id"] == task_id:
                events.append(OrchestratorEvent(**data))
        return tuple(events)

class PersistentTaskStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.tasks_dir = self.root / "tasks"
        self.tasks_dir.mkdir(exist_ok=True)
        self.audit = _PersistentAudit(self.root / "EVENTS.jsonl")
        self._records = {}
        self._load()

    def _path(self, task_id):
        return self.tasks_dir / f"{task_id}.json"

    def _write(self, record):
        payload = {"task": asdict(record.task), "state": record.state.value, "evidence": record.evidence}
        self._path(record.task.task_id).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _load(self):
        for path in self.tasks_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = payload["task"]
            task = TaskEnvelope(
                raw["task_id"], raw["type"], raw["priority"], raw["scope"],
                tuple(raw["allowed_actions"]), tuple(raw["forbidden_actions"]), raw["success_condition"],
            )
            self._records[task.task_id] = TaskRecord(task, TaskState(payload["state"]), payload["evidence"])

    def create(self, task):
        if task.task_id in self._records:
            raise ValueError(f"duplicate task_id: {task.task_id}")
        record = TaskRecord(task)
        self._records[task.task_id] = record
        self._write(record)
        self.audit.append(OrchestratorEvent(task_id=task.task_id, event_type="TASK_CREATED", actor="orchestrator", payload={"state": record.state.value}))
        return record

    def get(self, task_id):
        if task_id not in self._records:
            raise KeyError(task_id)
        return self._records[task_id]

    def transition(self, task_id, new_state, evidence=None):
        from orchestrator.memory.task_store import _ALLOWED
        record = self.get(task_id)
        if new_state not in _ALLOWED[record.state]:
            raise ValueError(f"illegal transition: {record.state.value} -> {new_state.value}")
        old = record.state
        record.state = new_state
        if evidence is not None:
            record.evidence.append(evidence)
        self._write(record)
        self.audit.append(OrchestratorEvent(task_id=task_id, event_type="STATE_TRANSITION", actor="orchestrator", payload={"from": old.value, "to": new_state.value, "evidence": evidence or {}}))
        return record

    def report(self, task_id):
        record = self.get(task_id)
        return {"task_id": task_id, "state": record.state.value, "evidence": list(record.evidence), "audit_events": len(self.audit.events(task_id))}
