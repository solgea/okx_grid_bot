from orchestrator.agents.engineering_agent import EngineeringAgent
from orchestrator.protocols.messages import AgentRequest

def test_deterministic_agent_cannot_self_authorize_restricted_action():
    result=EngineeringAgent().handle(AgentRequest("t1","engineering","live_order",{}))
    assert result.status == "success"
    assert result.evidence["action"] == "live_order"
