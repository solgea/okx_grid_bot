from orchestrator.core.state import TaskState
from orchestrator.protocols.messages import AgentRequest
from orchestrator.execution.dispatcher import ActionDispatcher

class MasterOrchestrator:
    def __init__(self, store, policy, dispatcher: ActionDispatcher, agents):
        self.store, self.policy, self.dispatcher, self.agents = store, policy, dispatcher, agents
    def submit(self, task): return self.store.create(task)
    def step(self, task_id):
        record = self.store.get(task_id)
        s = record.state
        if s == TaskState.RECEIVED: return self.store.transition(task_id, TaskState.OBSERVING, {"phase":"observe"})
        if s == TaskState.OBSERVING:
            result=self.dispatcher.dispatch(record.task,AgentRequest(task_id,"planner","read_repo",{}))
            return self.store.transition(task_id,TaskState.DIAGNOSING,result.evidence)
        if s == TaskState.DIAGNOSING: return self.store.transition(task_id,TaskState.PLANNING,{"phase":"diagnose"})
        if s == TaskState.PLANNING: return self.store.transition(task_id,TaskState.POLICY_CHECK,{"phase":"plan"})
        if s == TaskState.POLICY_CHECK:
            decision=self.policy.evaluate(record.task,"modify_code")
            if not decision.allowed: return self.store.transition(task_id,TaskState.BLOCKED,{"policy":decision.reason})
            return self.store.transition(task_id,TaskState.EXECUTING,{"policy":decision.reason})
        if s == TaskState.EXECUTING:
            result=self.dispatcher.dispatch(record.task,AgentRequest(task_id,"engineering","modify_code",{}))
            if result.status == "blocked": return self.store.transition(task_id,TaskState.BLOCKED,result.evidence)
            return self.store.transition(task_id,TaskState.VERIFYING,result.evidence)
        if s == TaskState.VERIFYING:
            result=self.dispatcher.dispatch(record.task,AgentRequest(task_id,"test","run_tests",{}))
            if result.status != "success": return self.store.transition(task_id,TaskState.DIAGNOSING,result.evidence)
            return self.store.transition(task_id,TaskState.REVIEWING,result.evidence)
        if s == TaskState.REVIEWING:
            result=self.dispatcher.dispatch(record.task,AgentRequest(task_id,"reviewer","review",{}))
            if result.status != "success": return self.store.transition(task_id,TaskState.DIAGNOSING,result.evidence)
            return self.store.transition(task_id,TaskState.COMMITTED,{"review":"passed"})
        if s == TaskState.COMMITTED: return self.store.transition(task_id,TaskState.REPORTED,{"reported":True})
        return record
    def run(self, task_id):
        for _ in range(20):
            record=self.step(task_id)
            if record.state in {TaskState.REPORTED,TaskState.BLOCKED}: return record
        raise RuntimeError("orchestrator lifecycle exceeded bounded step limit")
    def report(self, task_id):
        record=self.store.get(task_id)
        return {"task_id":task_id,"state":record.state.value,"evidence":list(record.evidence),"audit_events":len(self.store.audit.events(task_id))}
