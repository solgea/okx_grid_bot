import json
import os
import time
from dataclasses import dataclass
from urllib import error, request
from urllib.parse import urlencode


WORKFLOW_PATH = ".github/workflows/master-orchestrator.yml"
WORKFLOW_FILE = "master-orchestrator.yml"
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
    """Fail-closed adapter for the single Master Orchestrator workflow."""

    def __init__(self, owner, repo, token=None, opener=request.urlopen, sleeper=time.sleep):
        self.owner = owner
        self.repo = repo
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self._opener = opener
        self._sleeper = sleeper

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

    @staticmethod
    def _validate_task(task):
        if not isinstance(task, dict):
            raise GitHubActionsError("task envelope must be an object")
        serialized = json.dumps(task, sort_keys=True)
        if "GITHUB_TOKEN" in serialized or "ghp_" in serialized or "github_pat_" in serialized:
            raise GitHubActionsError("task envelope must not contain credentials")
        if "token" in task or "authorization" in task:
            raise GitHubActionsError("task envelope must not contain credentials")

    def dispatch(self, workflow, ref, task):
        self._validate_workflow(workflow)
        self._validate_task(task)
        task_id = task.get("task_id")
        if not task_id:
            raise GitHubActionsError("task_id is required")
        payload = {
            "ref": ref,
            "inputs": {
                "task_id": str(task_id),
                "task_json": json.dumps(task, sort_keys=True),
            },
        }
        status, _ = self._request(
            "POST",
            f"actions/workflows/{WORKFLOW_FILE}/dispatches",
            payload,
        )
        if status not in (201, 204):
            raise GitHubActionsError(f"workflow dispatch failed with HTTP {status}")
        return {"dispatched": True, "task_id": str(task_id), "workflow": WORKFLOW_PATH, "ref": ref}

    def find_run(self, task_id, ref):
        query = urlencode({"event": "workflow_dispatch", "branch": ref, "per_page": 20})
        status, payload = self._request(
            "GET",
            f"actions/workflows/{WORKFLOW_FILE}/runs?{query}",
        )
        if status != 200:
            raise GitHubActionsError(f"workflow run listing failed with HTTP {status}")
        expected_name = f"Master Orchestrator / {task_id}"
        for run in payload.get("workflow_runs", []):
            if str(run.get("name", "")) == expected_name:
                return WorkflowRunEvidence(
                    run_id=int(run["id"]),
                    status=str(run.get("status", "")),
                    conclusion=run.get("conclusion"),
                    url=run.get("html_url"),
                )
        return None

    def dispatch_and_find_run(self, workflow, ref, task, attempts=10, delay_seconds=1):
        self.dispatch(workflow, ref, task)
        for attempt in range(attempts):
            found = self.find_run(task["task_id"], ref)
            if found is not None:
                return found
            if attempt + 1 < attempts:
                self._sleeper(delay_seconds)
        raise GitHubActionsError("workflow dispatch accepted but run was not observable")

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
