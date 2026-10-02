from .base import DeterministicAgent
from orchestrator.protocols.messages import AgentResult

class TestAgent(DeterministicAgent):
    agent_id = "test"

    def __init__(self, executor=None):
        self.executor = executor

    def handle(self, request):
        if request.action != "run_tests" or self.executor is None:
            return super().handle(request)
        evidence = self.executor.run(request.context.get("command", "pytest -q"))
        return AgentResult(
            request.task_id,
            self.agent_id,
            "success" if evidence.passed else "failure",
            {"verification": {"passed": evidence.passed, "summary": evidence.summary, "details": evidence.details}},
        )
