import pytest
from orchestrator.protocols.messages import AgentRequest, AgentResult
from orchestrator.protocols.agent_protocol import AgentProtocol

def test_valid_message():
    r=AgentRequest("t1","planner","read_repo",{})
    AgentProtocol.validate_request(r)

def test_mismatched_task_rejected():
    req=AgentRequest("t1","planner","read_repo",{})
    with pytest.raises(ValueError): AgentProtocol.validate_result(AgentResult("t2","planner","success",{"x":1}),req)

def test_unknown_status_rejected():
    with pytest.raises(ValueError): AgentProtocol.validate_result(AgentResult("t1","planner","wat",{"x":1}))

def test_missing_evidence_rejected():
    with pytest.raises(ValueError): AgentProtocol.validate_result(AgentResult("t1","planner","success",{}))
