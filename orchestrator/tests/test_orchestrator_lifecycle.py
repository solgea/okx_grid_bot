from orchestrator.core.orchestrator import MasterOrchestrator
from orchestrator.core.policy import PolicyDecision
from orchestrator.core.task import TaskEnvelope
from orchestrator.execution.dispatcher import ActionDispatcher
from orchestrator.memory.task_store import TaskStore
from orchestrator.agents.planner_agent import PlannerAgent
from orchestrator.agents.engineering_agent import EngineeringAgent
from orchestrator.agents.test_agent import TestAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent

class Policy:
    def __init__(self,deny=None): self.deny=deny
    def evaluate(self,task,action): return PolicyDecision(action != self.deny,action,"denied" if action==self.deny else "allowed")

def make(deny=None):
    policy=Policy(deny); agents={"planner":PlannerAgent(),"engineering":EngineeringAgent(),"test":TestAgent(),"reviewer":ReviewerAgent()}
    return MasterOrchestrator(TaskStore(),policy,ActionDispatcher(agents,policy),agents)

def task(): return TaskEnvelope("t1","engineering_fix","blocking","single_failure",("read_repo","modify_code","run_tests","commit"),("live_exchange","merge_pr","deploy_production"),"github_ci_pass")

def test_successful_bounded_lifecycle():
    o=make(); r=o.submit(task()); final=o.run(r.task.task_id); assert final.state.value=="REPORTED"

def test_policy_denial_blocks():
    o=make("modify_code"); r=o.submit(task()); final=o.run(r.task.task_id); assert final.state.value=="BLOCKED"
