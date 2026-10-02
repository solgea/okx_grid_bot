from typing import Protocol
from orchestrator.protocols.messages import AgentRequest, AgentResult
from orchestrator.protocols.agent_protocol import AgentProtocol

class Agent(Protocol):
    agent_id: str
    def handle(self, request: AgentRequest) -> AgentResult: ...

class DeterministicAgent:
    agent_id = "base"
    def handle(self, request):
        AgentProtocol.validate_request(request)
        return AgentResult(request.task_id,self.agent_id,"success",{"action":request.action,"deterministic":True,"verification":{"passed":request.action == "run_tests"}})
