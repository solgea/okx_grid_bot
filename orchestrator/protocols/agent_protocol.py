from .messages import AgentRequest, AgentResult

VALID_STATUSES = frozenset({"success", "failure", "blocked"})

class AgentProtocol:
    @staticmethod
    def validate_request(request: AgentRequest) -> None:
        if not request.task_id or not request.agent_id or not request.action:
            raise ValueError("request requires task_id, agent_id, and action")
        if not isinstance(request.context, dict):
            raise TypeError("request context must be a dict")

    @staticmethod
    def validate_result(result: AgentResult, request: AgentRequest | None = None) -> None:
        if request is not None and result.task_id != request.task_id:
            raise ValueError("result task_id does not match request")
        if result.status not in VALID_STATUSES:
            raise ValueError(f"unknown agent status: {result.status}")
        if not isinstance(result.evidence, dict) or not result.evidence:
            raise ValueError("agent result requires evidence")
