import pytest
from orchestrator.runtime.intake import TaskIntake

def test_live_exchange_never_enters_allowed_actions():
    payload={"task_id":"safe-1","type":"engineering_fix","priority":"blocking","scope":"single_failure","allowed_actions":["live_order"],"forbidden_actions":[],"success_condition":"github_ci_pass"}
    with pytest.raises(ValueError): TaskIntake().validate(payload)
