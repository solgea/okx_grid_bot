import pytest
from orchestrator.runtime.intake import TaskIntake
from orchestrator.runtime.store import PersistentTaskStore
from orchestrator.core.state import TaskState

VALID={"task_id":"rt-1","type":"engineering_fix","priority":"blocking","scope":"single_failure","allowed_actions":["read_repo","modify_code","run_tests","commit"],"forbidden_actions":["live_exchange","merge_pr"],"success_condition":"github_ci_pass"}

def test_intake_and_persistence(tmp_path):
    task=TaskIntake().validate(VALID); store=PersistentTaskStore(tmp_path); record=store.create(task)
    store.transition(task.task_id, TaskState.OBSERVING, {"phase":"observe"})
    reopened=PersistentTaskStore(tmp_path)
    assert reopened.get(task.task_id).state is TaskState.OBSERVING
    assert len(reopened.audit.events(task.task_id)) == 2

def test_invalid_and_restricted_rejected():
    with pytest.raises(ValueError): TaskIntake().validate({"task_id":"x"})
    bad=dict(VALID, allowed_actions=["live_order"])
    with pytest.raises(ValueError): TaskIntake().validate(bad)

def test_duplicate_task_id_rejected(tmp_path):
    store=PersistentTaskStore(tmp_path); task=TaskIntake().validate(VALID); store.create(task)
    with pytest.raises(ValueError): store.create(task)
