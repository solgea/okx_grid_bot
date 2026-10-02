import json
import os
from dataclasses import dataclass
from urllib import error, request


WORKFLOW_PATH = ".github/workflows/master-orchestrator.yml"
API_BASE = "https://api.github.com"


class GitHubActionsError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkflowRunEvidence:
    run_id: int
    status: str
    conclusion: str | None
    url: str | None


class GitHubActionsBridge:
    """Fail-closed adapter for the single repository orchestrator workflow."""

    def __init__(self, owner, repo, token=None, opener=request.urlopen):
        self.owner = owner
        self.repo = repo
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self._opener = opener

    def _request(self, method, path, payload=None):
        if not self.token:
            raise GitHubActionsError("GitHub authentication is not configured")
        url = f"{API_BASE}/repos/{self.owner}/{self.repo}/{path.lstrip('/')}"
        body = None if payload is None else json.dumps(payload).encode()
        req = request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            raise GitHubActionsError(f"GitHub API HTTP {exc.code}") from exc
        except (error.URLError, TimeoutError) as exc:
            raise GitHubActionsError("GitHub API network failure") from exc

    @staticmethod
    def _validate_workflow(workflow):
        if workflow != WORKFLOW_PATH:
            raise GitHubActionsError("workflow is not the approved Master Orchestrator workflow")

    def dispatch(self, workflow, ref, task_json):
        self._validate_workflow(workflow)
        if not isinstance(task_json, dict):
            raise GitHubActionsError("task_json must be an object")
        if "GITHUB_TOKEN" in json.dumps(task_json) or "token" in task_json:
            raise GitHubActionsError("task envelope must not contain credentials")
        payload = {"ref": ref, "inputs": {"task_json": json.dumps(task_json, sort_keys=True)}}
        status, _ = self._request(
            "POST",
            f"actions/workflows/{WORKFLOW_PATH.rsplit('/', 1)[-1]}/dispatches",
            payload,
        )
        if status not in (201, 204):
            raise GitHubActionsError(f"workflow dispatch failed with HTTP {status}")
        return {"dispatched": True, "workflow": WORKFLOW_PATH, "ref": ref}

    def observe_run(self, run_id):
        status, payload = self._request("GET", f"actions/runs/{int(run_id)}")
        if status != 200:
            raise GitHubActionsError(f"workflow run lookup failed with HTTP {status}")
        return WorkflowRunEvidence(
            run_id=int(payload["id"]),
            status=str(payload.get("status", "")),
            conclusion=payload.get("conclusion"),
            url=payload.get("html_url"),
        )
