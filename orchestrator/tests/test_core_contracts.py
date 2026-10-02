from dataclasses import FrozenInstanceError

import pytest

from orchestrator.core.policy import DefaultPolicyEngine, PolicyDecision
from orchestrator.core.state import TaskState
from orchestrator.core.task import TaskEnvelope


def make_task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="G8-PF031",
        type="engineering_fix",
        priority="blocking",
        scope="single_failure",
        allowed_actions=("read_repo", "modify_code", "run_tests", "commit"),
        forbidden_actions=("live_exchange", "merge_pr", "deploy_production"),
        success_condition="github_ci_pass",
    )


def test_task_envelope_is_immutable_and_preserves_contract():
    task = make_task()
    assert task.task_id == "G8-PF031"
    assert task.allowed_actions == ("read_repo", "modify_code", "run_tests", "commit")
    assert task.forbidden_actions == ("live_exchange", "merge_pr", "deploy_production")
    with pytest.raises(FrozenInstanceError):
        task.task_id = "other"


def test_task_states_include_full_lifecycle_and_terminals():
    assert TaskState.RECEIVED.value == "RECEIVED"
    assert TaskState.POLICY_CHECK.value == "POLICY_CHECK"
    assert TaskState.REPORTED.value == "REPORTED"
    assert TaskState.BLOCKED.value == "BLOCKED"


def test_default_policy_denies_restricted_actions_even_if_requested():
    decision=DefaultPolicyEngine().evaluate(make_task(), "live_order")
    assert decision.allowed is False

def test_policy_decision_is_explicit():
    decision = PolicyDecision(allowed=False, action="live_exchange", reason="restricted action")
    assert decision.allowed is False
    assert decision.action == "live_exchange"
    assert decision.reason == "restricted action"
