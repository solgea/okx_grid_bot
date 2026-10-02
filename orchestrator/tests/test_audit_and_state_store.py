import pytest
from orchestrator.core.events import OrchestratorEvent
from orchestrator.core.state import TaskState
from orchestrator.core.task import TaskEnvelope
from orchestrator.memory.audit_log import AuditLog
from orchestrator.memory.task_store import TaskStore

def task(): return TaskEnvelope("t1","engineering_fix","blocking","single_failure",("read_repo","modify_code"),("live_exchange","merge_pr"),"github_ci_pass")

def test_duplicate_event_ids_rejected():
    log=AuditLog(); event=OrchestratorEvent(event_id="e1",task_id="t1")
    log.append(event)
    with pytest.raises(ValueError): log.append(event)

def test_state_store_enforces_legal_transitions():
    store=TaskStore(); store.create(task())
    store.transition("t1",TaskState.OBSERVING)
    with pytest.raises(ValueError): store.transition("t1",TaskState.REPORTED)
