from orchestrator.protocols.messages import AgentRequest, AgentResult
from orchestrator.protocols.agent_protocol import AgentProtocol

class ActionDispatcher:
    def __init__(self, agents, policy):
        self.agents = agents
        self.policy = policy
    def dispatch(self, task, request: AgentRequest) -> AgentResult:
        AgentProtocol.validate_request(request)
        decision = self.policy.evaluate(task, request.action)
        if not decision.allowed:
            return AgentResult(task.task_id, request.agent_id, "blocked", {"policy": decision.reason, "action": request.action})
        agent = self.agents[request.agent_id]
        result = agent.handle(request)
        AgentProtocol.validate_result(result, request)
        return result
