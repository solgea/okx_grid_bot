import pytest
from orchestrator.execution.git import GitExecutor

def test_git_executor_allowlist():
    with pytest.raises(PermissionError): GitExecutor().run("push")
