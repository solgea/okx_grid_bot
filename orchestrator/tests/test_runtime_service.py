from orchestrator.runtime.service import RuntimeService
from orchestrator.core.policy import DefaultPolicyEngine
from orchestrator.execution.dispatcher import ActionDispatcher
from orchestrator.agents.planner_agent import PlannerAgent
from orchestrator.agents.engineering_agent import EngineeringAgent
from orchestrator.agents.test_agent import TestAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent
from orchestrator.execution.ci import VerificationEvidence

class FakeExecutor:
    def run(self, command):
        return VerificationEvidence(True, "tests passed", {"command": command})

def _payload(task_id):
    return {"task_id":task_id,"type":"engineering_fix","priority":"blocking","scope":"single_failure","allowed_actions":["read_repo","modify_code","run_tests","commit"],"forbidden_actions":["live_exchange","merge_pr"],"success_condition":"github_ci_pass"}

def test_runtime_lifecycle(tmp_path):
    policy=DefaultPolicyEngine()
    agents={"planner":PlannerAgent(),"engineering":EngineeringAgent(),"test":TestAgent(FakeExecutor()),"reviewer":ReviewerAgent()}
    service=RuntimeService(tmp_path,policy,ActionDispatcher(agents,policy),agents,commit_executor=lambda _: {"passed":True,"commit_sha":"abc123"})
    final=service.run(service.submit(_payload("rt-service")).task.task_id)
    assert final.state.value == "REPORTED"
    assert service.report("rt-service")["audit_events"] >= 10

def test_missing_commit_blocks(tmp_path):
    policy=DefaultPolicyEngine()
    agents={"planner":PlannerAgent(),"engineering":EngineeringAgent(),"test":TestAgent(FakeExecutor()),"reviewer":ReviewerAgent()}
    service=RuntimeService(tmp_path,policy,ActionDispatcher(agents,policy),agents,commit_executor=lambda _: {"passed":True})
    final=service.run(service.submit(_payload("rt-block")).task.task_id)
    assert final.state.value == "BLOCKED"
