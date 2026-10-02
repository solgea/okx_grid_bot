import json
from urllib import error
from unittest.mock import Mock

import pytest

from orchestrator.execution.github_actions import GitHubActionsBridge, GitHubActionsError, WORKFLOW_PATH


class Response:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_dispatch_uses_only_approved_workflow():
    opener = Mock(return_value=Response(204, {}))
    bridge = GitHubActionsBridge("owner", "repo", token="secret", opener=opener)

    result = bridge.dispatch(WORKFLOW_PATH, "main", {"task_id": "T-1"})

    assert result["dispatched"] is True
    req = opener.call_args.args[0]
    assert req.full_url.endswith("/actions/workflows/master-orchestrator.yml/dispatches")


def test_forbidden_workflow_is_rejected_before_api_call():
    opener = Mock()
    bridge = GitHubActionsBridge("owner", "repo", token="secret", opener=opener)

    with pytest.raises(GitHubActionsError, match="approved Master Orchestrator workflow"):
        bridge.dispatch(".github/workflows/other.yml", "main", {"task_id": "T-1"})

    opener.assert_not_called()


def test_missing_authentication_fails_closed():
    bridge = GitHubActionsBridge("owner", "repo", token=None, opener=Mock())

    with pytest.raises(GitHubActionsError, match="authentication"):
        bridge.dispatch(WORKFLOW_PATH, "main", {"task_id": "T-1"})


def test_api_failure_is_normalized():
    def fail(_request, timeout):
        raise error.URLError("offline")

    bridge = GitHubActionsBridge("owner", "repo", token="secret", opener=fail)

    with pytest.raises(GitHubActionsError, match="network failure"):
        bridge.dispatch(WORKFLOW_PATH, "main", {"task_id": "T-1"})


def test_task_credentials_are_rejected():
    bridge = GitHubActionsBridge("owner", "repo", token="secret", opener=Mock())

    with pytest.raises(GitHubActionsError, match="credentials"):
        bridge.dispatch(WORKFLOW_PATH, "main", {"task_id": "T-1", "token": "do-not-store"})


def test_run_observation_returns_status_and_conclusion():
    opener = Mock(return_value=Response(200, {
        "id": 123,
        "status": "completed",
        "conclusion": "failure",
        "html_url": "https://github.com/owner/repo/actions/runs/123",
    }))
    bridge = GitHubActionsBridge("owner", "repo", token="secret", opener=opener)

    evidence = bridge.observe_run(123)

    assert evidence.run_id == 123
    assert evidence.status == "completed"
    assert evidence.conclusion == "failure"
    assert evidence.url.endswith("/123")


def test_failed_run_is_not_success():
    opener = Mock(return_value=Response(200, {
        "id": 124,
        "status": "completed",
        "conclusion": "failure",
    }))
    bridge = GitHubActionsBridge("owner", "repo", token="secret", opener=opener)

    evidence = bridge.observe_run(124)

    assert evidence.conclusion != "success"
