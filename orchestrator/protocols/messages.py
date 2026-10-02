from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class AgentRequest:
    task_id: str
    agent_id: str
    action: str
    context: dict

@dataclass(frozen=True, slots=True)
class AgentResult:
    task_id: str
    agent_id: str
    status: str
    evidence: dict
    next_action: str | None = None
