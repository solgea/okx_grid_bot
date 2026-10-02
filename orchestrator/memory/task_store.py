from dataclasses import dataclass, field
from orchestrator.core.state import TaskState
from orchestrator.core.task import TaskEnvelope
from orchestrator.core.events import OrchestratorEvent
from .audit_log import AuditLog

_ALLOWED = {
    TaskState.RECEIVED: {TaskState.OBSERVING, TaskState.BLOCKED},
    TaskState.OBSERVING: {TaskState.DIAGNOSING, TaskState.BLOCKED},
    TaskState.DIAGNOSING: {TaskState.PLANNING, TaskState.BLOCKED},
    TaskState.PLANNING: {TaskState.POLICY_CHECK, TaskState.BLOCKED},
    TaskState.POLICY_CHECK: {TaskState.EXECUTING, TaskState.BLOCKED},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.DIAGNOSING, TaskState.BLOCKED},
    TaskState.VERIFYING: {TaskState.REVIEWING, TaskState.DIAGNOSING, TaskState.BLOCKED},
    TaskState.REVIEWING: {TaskState.COMMITTED, TaskState.DIAGNOSING, TaskState.BLOCKED},
    TaskState.COMMITTED: {TaskState.REPORTED},
    TaskState.REPORTED: set(),
    TaskState.BLOCKED: set(),
}

@dataclass
class TaskRecord:
    task: TaskEnvelope
    state: TaskState = TaskState.RECEIVED
    evidence: list[dict] = field(default_factory=list)

class TaskStore:
    def __init__(self, audit: AuditLog | None = None):
        self._records = {}
        self.audit = audit or AuditLog()
    def create(self, task: TaskEnvelope) -> TaskRecord:
        if task.task_id in self._records:
            raise ValueError(f"duplicate task_id: {task.task_id}")
        record = TaskRecord(task)
        self._records[task.task_id] = record
        self.audit.append(OrchestratorEvent(task_id=task.task_id,event_type="TASK_CREATED",actor="orchestrator",payload={"state":record.state.value}))
        return record
    def get(self, task_id: str) -> TaskRecord:
        if task_id not in self._records:
            raise KeyError(task_id)
        return self._records[task_id]
    def transition(self, task_id: str, new_state: TaskState, evidence=None) -> TaskRecord:
        record = self.get(task_id)
        if new_state not in _ALLOWED[record.state]:
            raise ValueError(f"illegal transition: {record.state.value} -> {new_state.value}")
        old = record.state
        record.state = new_state
        if evidence is not None: record.evidence.append(evidence)
        self.audit.append(OrchestratorEvent(task_id=task_id,event_type="STATE_TRANSITION",actor="orchestrator",payload={"from":old.value,"to":new_state.value,"evidence":evidence or {}}))
        return record
