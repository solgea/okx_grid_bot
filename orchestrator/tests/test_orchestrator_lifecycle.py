from orchestrator.core.orchestrator import MasterOrchestrator
from orchestrator.core.policy import PolicyDecision
from orchestrator.core.task import TaskEnvelope
from orchestrator.execution.dispatcher import ActionDispatcher
from orchestrator.memory.task_store import TaskStore
from orchestrator.agents.planner_agent import PlannerAgent
from orchestrator.agents.engineering_agent import EngineeringAgent
from orchestrator.agents.test_agent import TestAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent
from orchestrator.execution.ci import VerificationEvidence

class FakeTestExecutor:
    def run(self, command):
        return VerificationEvidence(True, "tests passed", {"command": command})

class Policy:
    def __init__(self, deny=None): self.deny = deny
    def evaluate(self, task, action):
        return PolicyDecision(action != self.deny, action, "denied" if action == self.deny else "allowed")

def commit_ok(_task_id):
    return {"passed": True, "commit_sha": "abc123"}

def commit_missing(_task_id):
    return {"passed": True}

def make(deny=None, commit_executor=commit_ok):
    policy = Policy(deny)
    agents = {
        "planner": PlannerAgent(),
        "engineering": EngineeringAgent(),
        "test": TestAgent(FakeTestExecutor()),
        "reviewer": ReviewerAgent(),
    }
    return MasterOrchestrator(TaskStore(), policy, ActionDispatcher(agents, policy), agents, commit_executor=commit_executor)

def task():
    return TaskEnvelope(
        "t1", "engineering_fix", "blocking", "single_failure",
        ("read_repo", "modify_code", "run_tests", "commit"),
        ("live_exchange", "merge_pr", "deploy_production"),
        "github_ci_pass",
    )

def test_successful_bounded_lifecycle():
    o = make()
    r = o.submit(task())
    final = o.run(r.task.task_id)
    assert final.state.value == "REPORTED"
    assert any(e.get("verification", {}).get("passed") for e in final.evidence)
    assert any(e.get("commit", {}).get("commit_sha") for e in final.evidence)

def test_policy_denial_blocks():
    o = make("modify_code")
    r = o.submit(task())
    final = o.run(r.task.task_id)
    assert final.state.value == "BLOCKED"

def test_missing_commit_evidence_blocks():
    o = make(commit_executor=commit_missing)
    r = o.submit(task())
    final = o.run(r.task.task_id)
    assert final.state.value == "BLOCKED"
