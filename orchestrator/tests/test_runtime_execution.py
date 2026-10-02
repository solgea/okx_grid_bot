from types import SimpleNamespace

from orchestrator.execution.runtime import build_commit_executor, build_test_executor
from orchestrator.agents.test_agent import TestAgent


def test_runtime_test_executor_runs_real_command():
    agent = TestAgent(build_test_executor())
    result = agent.handle(SimpleNamespace(
        task_id="T-1",
        agent_id="test",
        action="run_tests",
        context={"command": "python -c \"print('ok')\""},
    ))

    assert result.status == "success"
    assert result.evidence["verification"]["passed"] is True


def test_commit_executor_fails_closed_without_changes():
    class Git:
        def read(self):
            return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = build_commit_executor(Git())("T-1")

    assert result["passed"] is False
    assert "no repository changes" in result["reason"]
