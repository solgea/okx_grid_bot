"""Tests for the Engineering Agent same-failure counter (workflow shell logic).

The workflow's inline shell steps are extracted from the YAML and executed with
bash in a temp dir, so the real counter/limit logic is what is under test.
Skipped on Windows (no reliable bash); CI runs these on Linux.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="requires a POSIX bash",
)

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "engineering-agent-dispatch.yml"
STATE_KEYS = [
    "status", "phase", "gate", "pr", "head_branch", "last_ci_run", "last_ci_conclusion",
    "last_blocker", "same_failure_attempts", "max_same_failure_attempts",
    "live_trading_allowed", "auto_merge_allowed",
]


def _steps():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return {s["name"]: s for s in data["jobs"]["agent"]["steps"]}


def _state_text(last_blocker="none", attempts=0, max_n=2):
    return (
        "# Engineering Agent State\n\nstatus: ACTIVE\nphase: 3\ngate: G8\npr: 24\n"
        "head_branch: b\nlast_ci_run: 1\nlast_ci_conclusion: failure\n"
        f"last_blocker: {last_blocker}\nsame_failure_attempts: {attempts}\n"
        f"max_same_failure_attempts: {max_n}\nlive_trading_allowed: false\n"
        "auto_merge_allowed: false\n\nCI and repository evidence take precedence over this state file.\n"
    )


class Sandbox:
    def __init__(self, tmp_path, state=None):
        self.dir = tmp_path
        (tmp_path / "agent" / "runtime").mkdir(parents=True)
        if state is not None:
            (tmp_path / "agent" / "STATE.md").write_text(state, encoding="utf-8")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text('#!/bin/bash\nif [ "$1 $2" = "run view" ]; then echo failure; fi\nexit 0\n')
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.env = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "GITHUB_ENV": str(tmp_path / "gh_env"),
            "TASK_ID": "CI-G8-AUTO", "TASK_ISSUE": "", "PR_NUMBER": "24", "HEAD_BRANCH": "b",
            "CI_RUN_ID": "", "EVENT_NAME": "workflow_run", "TRIGGER_CI_CONCLUSION": "",
            "VALIDATION": "skipped", "RUNTIME_OUTCOME": "not-run", "AGENT_MESSAGE": "m", "PUSH_TOKEN": "",
            "DEFAULT_BRANCH": "main", "AGENT_OUTCOME": "not-run", "PUBLISH_OUTCOME": "not-run",
            "POLICY_REJECTED": "false", "POLICY_REASON": "none", "POLICY_REVIEW": "false",
            "GITHUB_OUTPUT": str(tmp_path / "gh_out"), "GITHUB_REPOSITORY": "o/r",
        }
        Path(self.env["GITHUB_OUTPUT"]).write_text("")
        Path(self.env["GITHUB_ENV"]).write_text("")

    def failure_log(self, text):
        (self.dir / "agent" / "runtime" / "CI_FAILURE.log").write_text(text, encoding="utf-8")

    def run(self, step, **extra):
        self.env.update(extra)
        script = _steps()[step]["run"]
        proc = subprocess.run(["bash", "-c", script], cwd=self.dir, env=self.env,
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        # emulate GITHUB_ENV propagation to later steps
        for line in Path(self.env["GITHUB_ENV"]).read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                self.env[k] = v
        return proc

    def state(self):
        out = {}
        for line in (self.dir / "agent" / "STATE.md").read_text().splitlines():
            if ":" in line and not line.startswith("#"):
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
        return out


FAIL_A = "test\tTests\t2026-10-03T10:31:56.7302387Z FAILED tests/test_x.py::test_a - AssertionError: 5 != 6\n"
FAIL_A_LATER = "test\tTests\t2026-10-03T11:45:01.1111111Z FAILED tests/test_x.py::test_a - AssertionError: 9 != 7\n"
FAIL_B = "test\tTests\t2026-10-03T10:31:56.7302387Z FAILED tests/test_y.py::test_b - KeyError: 'x'\n"


def cycle(box, log, ci="failure"):
    """One autonomous workflow_run cycle: signature -> limit check -> persist."""
    box.failure_log(log)
    box.run("Compute blocker signature", TRIGGER_CI_CONCLUSION=ci)
    box.run("Enforce same-failure limit")
    box.run("Persist agent state and report", CI_RUN_ID="")
    return box.state()


def test_signature_is_stable_across_timestamps_and_numbers(tmp_path):
    a = Sandbox(tmp_path / "a", _state_text())
    b = Sandbox(tmp_path / "b", _state_text())
    a.failure_log(FAIL_A); b.failure_log(FAIL_A_LATER)
    a.run("Compute blocker signature", TRIGGER_CI_CONCLUSION="failure")
    b.run("Compute blocker signature", TRIGGER_CI_CONCLUSION="failure")
    assert a.env["BLOCKER_SIG"] == b.env["BLOCKER_SIG"] and a.env["BLOCKER_SIG"].startswith("ci:")


def test_different_failures_have_different_signatures(tmp_path):
    a = Sandbox(tmp_path / "a", _state_text()); b = Sandbox(tmp_path / "b", _state_text())
    a.failure_log(FAIL_A); b.failure_log(FAIL_B)
    a.run("Compute blocker signature", TRIGGER_CI_CONCLUSION="failure")
    b.run("Compute blocker signature", TRIGGER_CI_CONCLUSION="failure")
    assert a.env["BLOCKER_SIG"] != b.env["BLOCKER_SIG"]


def test_success_has_no_blocker(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    box.run("Compute blocker signature", TRIGGER_CI_CONCLUSION="success")
    assert box.env["BLOCKER_SIG"] == "none"


def test_counter_increments_and_blocks_on_third_recurrence(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    s1 = cycle(box, FAIL_A)
    assert s1["same_failure_attempts"] == "1" and s1["status"] == "ACTIVE"
    sig = s1["last_blocker"]
    assert sig.startswith("ci:") and box.env["AGENT_LIMIT_REACHED"] == "false"

    s2 = cycle(box, FAIL_A_LATER)                      # 2nd attempt still allowed
    assert s2["same_failure_attempts"] == "2" and s2["last_blocker"] == sig
    assert box.env["AGENT_LIMIT_REACHED"] == "false"

    s3 = cycle(box, FAIL_A)                            # 3rd: limit reached, no new attempt
    assert box.env["AGENT_LIMIT_REACHED"] == "true"
    assert s3["status"] == "BLOCKED" and s3["same_failure_attempts"] == "2"
    assert "No change made" in (box.dir / "agent" / "REPORT.md").read_text()


def test_new_failure_resets_counter_to_one(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    cycle(box, FAIL_A); cycle(box, FAIL_A)
    s = cycle(box, FAIL_B)
    assert s["same_failure_attempts"] == "1" and box.env["AGENT_LIMIT_REACHED"] == "false"


def test_green_ci_clears_the_counter(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    cycle(box, FAIL_A); cycle(box, FAIL_A)
    s = cycle(box, "", ci="success")
    assert s["last_blocker"] == "none" and s["same_failure_attempts"] == "0" and s["status"] == "ACTIVE"


def test_human_dispatch_is_never_limited(tmp_path):
    box = Sandbox(tmp_path, _state_text(last_blocker="ci:abc", attempts=5))
    box.run("Enforce same-failure limit", EVENT_NAME="workflow_dispatch", BLOCKER_SIG="ci:abc")
    assert box.env["AGENT_LIMIT_REACHED"] == "false"


@pytest.mark.parametrize("garbage", ["", "abc", "-1", "2.5"])
def test_garbage_state_values_fall_back_safely(tmp_path, garbage):
    box = Sandbox(tmp_path, _state_text(last_blocker="x", attempts=garbage, max_n=garbage))
    box.run("Enforce same-failure limit", BLOCKER_SIG="ci:abc")
    assert box.env["PREV_ATTEMPTS"] == "0" and box.env["MAX_ATTEMPTS"] == "2"
    assert box.env["AGENT_LIMIT_REACHED"] == "false"


def test_missing_state_file_is_handled(tmp_path):
    box = Sandbox(tmp_path, None)
    box.run("Enforce same-failure limit", BLOCKER_SIG="ci:abc")
    assert box.env["PREV_ATTEMPTS"] == "0" and box.env["AGENT_LIMIT_REACHED"] == "false"


def test_readonly_task_counts_failures_and_clears_on_pass(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    box.run("Persist agent state and report", TASK_ID="EA-OKX-READONLY-001", RUNTIME_OUTCOME="failure",
            BLOCKER_SIG="none")
    s = box.state()
    assert s["last_blocker"] == "readonly:BLOCKED_OR_FAIL" and s["same_failure_attempts"] == "1"
    assert s["status"] == "BLOCKED"

    box.env.update({"PREV_SIG": "readonly:BLOCKED_OR_FAIL", "PREV_ATTEMPTS": "1"})
    box.run("Persist agent state and report", TASK_ID="EA-OKX-READONLY-001", RUNTIME_OUTCOME="failure")
    assert box.state()["same_failure_attempts"] == "2"

    (box.dir / "agent" / "runtime" / "OKX_READONLY_RESULT").write_text("OKX_DEMO_READ_ONLY=PASS\n")
    box.run("Persist agent state and report", TASK_ID="EA-OKX-READONLY-001", RUNTIME_OUTCOME="success")
    s = box.state()
    assert s["last_blocker"] == "none" and s["same_failure_attempts"] == "0" and s["status"] == "ACTIVE"


def test_state_schema_is_unchanged_for_the_monitoring_tools(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    cycle(box, FAIL_A)
    keys = set(box.state())
    assert set(STATE_KEYS) <= keys                       # everything the monitors read is present
    assert keys - set(STATE_KEYS) == {"task_id", "issue", "readonly_runtime"}  # pre-existing extras only
    assert box.state()["live_trading_allowed"] == "false" and box.state()["auto_merge_allowed"] == "false"


def test_agent_steps_are_skipped_when_limit_reached():
    steps = _steps()
    for name in ["Install Groq coding agent", "Build agent prompt", "Run Groq engineering agent",
                 "Check agent change policy", "Validate agent result"]:
        assert "env.AGENT_LIMIT_REACHED != 'true'" in steps[name]["if"], name
    assert "steps.validate.outputs.changed == 'true'" in steps["Publish normal agent change"]["if"]
    assert "steps.policy.outputs.rejected != 'true'" in steps["Validate agent result"]["if"]


def test_agent_cannot_rewrite_its_own_counter():
    assert "git checkout -- \"$F\"" in _steps()["Check agent change policy"]["run"]


# --- hardening: trigger, policy gate, chain guard, honest status, branch guards ---
import json as _json
import textwrap


def _job():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["agent"]


def test_autonomous_chain_only_starts_from_failed_ci():
    cond = _job()["if"]
    assert "workflow_run.conclusion == 'failure'" in cond and "!= 'cancelled'" not in cond
    assert not (WORKFLOW.parent / "ea-dispatch-probe.yml").exists()
    group = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["concurrency"]
    assert "pull_requests[0].number" in group["group"] and group["cancel-in-progress"] is False


def test_no_expression_interpolation_of_repository_in_shell():
    for name in ("Publish normal agent change", "Persist agent state and report"):
        assert "${{ github.repository }}" not in _steps()[name]["run"]


def init_repo(box, files=None):
    files = files or {
        "app.py": "x = 1\n",
        "tests/test_a.py": "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n",
        "Dockerfile": "FROM python:3.12\n",
        ".github/workflows/ci.yml": "name: CI\n",
        "requirements.txt": "pytest\n",
        "scripts/tool.py": "y = 1\n",
        "preflight_layer/v.py": "z = 1\n",
    }
    for rel, text in files.items():
        path = box.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git = lambda *a, **k: subprocess.run(["git", *a], cwd=box.dir, check=True, capture_output=True, **k)
    git("init", "-q")
    git("config", "user.name", "tester"); git("config", "user.email", "t@t")
    git("add", "-A"); git("commit", "-qm", "base")
    return git


def policy(box):
    Path(box.env["GITHUB_OUTPUT"]).write_text("")
    box.run("Check agent change policy")
    return dict(line.split("=", 1) for line in Path(box.env["GITHUB_OUTPUT"]).read_text().split() if "=" in line)


def test_policy_allows_a_small_scoped_fix(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    (box.dir / "app.py").write_text("x = 2\n")
    (box.dir / "newmod.py").write_text("a = 1\n")            # untracked new file counts as a change
    out = policy(box)
    assert out["changed"] == "true" and out["rejected"] == "false" and out["reason"] == "none"


def test_policy_detects_untracked_only_changes(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    (box.dir / "extra.py").write_text("a = 1\n")
    assert policy(box)["changed"] == "true"


def test_policy_reports_no_change(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    out = policy(box)
    assert out["changed"] == "false" and out["rejected"] == "false"


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", "Dockerfile", "requirements.txt", "scripts/tool.py",
                                  "scripts/new.py", ".env", "AGENTS.md", "agent/POLICY.md", ".github/workflows/new.yml"])
def test_policy_rejects_denied_paths(tmp_path, path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    (box.dir / path).parent.mkdir(parents=True, exist_ok=True)
    (box.dir / path).write_text("changed\n")
    out = policy(box)
    assert out["rejected"] == "true" and out["reason"] == "denied-path"


def test_policy_rejects_renaming_a_protected_file(tmp_path):
    box = Sandbox(tmp_path, _state_text()); git = init_repo(box)
    git("mv", "Dockerfile", "app_docker.txt")
    assert policy(box)["reason"] == "denied-path"


def test_policy_rejects_removed_or_reduced_tests(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    (box.dir / "tests/test_a.py").write_text("def test_one():\n    pass\n")      # one test removed
    assert policy(box)["reason"] == "tests-reduced"
    (box.dir / "tests/test_a.py").unlink()                                       # file deleted
    assert policy(box)["reason"] == "tests-reduced"


def test_policy_allows_adding_tests(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    (box.dir / "tests/test_b.py").write_text("def test_new():\n    pass\n")
    assert policy(box)["rejected"] == "false"


def test_policy_rejects_oversized_changes(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    (box.dir / "big.py").write_text("v = 1\n" * 400)
    assert policy(box)["reason"] == "too-large"
    (box.dir / "big.py").unlink()
    for i in range(9):
        (box.dir / f"m{i}.py").write_text("a = 1\n")
    assert policy(box)["reason"] == "too-large"


def test_policy_flags_safety_critical_paths_for_review(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    (box.dir / "preflight_layer/v.py").write_text("z = 2\n")
    out = policy(box)
    assert out["rejected"] == "false" and out["review"] == "true"


def test_policy_reverts_agent_edits_to_state_and_report(tmp_path):
    box = Sandbox(tmp_path, _state_text(last_blocker="ci:abc", attempts=2)); init_repo(box)
    (box.dir / "agent" / "STATE.md").write_text(_state_text(last_blocker="none", attempts=0))
    out = policy(box)
    assert out["changed"] == "false"
    assert box.state()["same_failure_attempts"] == "2"


def _commits(box, subjects_authors):
    for subject, author in subjects_authors:
        _commits.n = getattr(_commits, "n", 0) + 1
        (box.dir / "f.txt").write_text(f"{subject}\n{_commits.n}\n")
        subprocess.run(["git", "add", "-A"], cwd=box.dir, check=True, capture_output=True)
        subprocess.run(["git", "-c", f"user.name={author}", "-c", "user.email=a@a", "commit", "-qm", subject],
                       cwd=box.dir, check=True, capture_output=True)


def test_chain_guard_stops_after_three_consecutive_agent_fixes(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    A = "okx-engineering-agent"
    _commits(box, [("agent: fix first CI blocker", A), ("agent: persist task state and report [skip ci]", A),
                   ("agent: fix first CI blocker", A), ("agent: fix first CI blocker", A)])
    box.run("Enforce same-failure limit", BLOCKER_SIG="ci:new1")
    assert box.env["AGENT_LIMIT_REACHED"] == "true" and box.env["LIMIT_REASON"] == "chain"


def test_chain_guard_allows_two_fixes_and_resets_on_human_commit(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    A = "okx-engineering-agent"
    _commits(box, [("agent: fix first CI blocker", A), ("agent: fix first CI blocker", A)])
    box.run("Enforce same-failure limit", BLOCKER_SIG="ci:new1")
    assert box.env["AGENT_LIMIT_REACHED"] == "false"
    _commits(box, [("agent: fix first CI blocker", A), ("human change", "soner")])
    box.run("Enforce same-failure limit", BLOCKER_SIG="ci:new1")
    assert box.env["AGENT_LIMIT_REACHED"] == "false"


def test_chain_guard_does_not_apply_to_human_dispatch(tmp_path):
    box = Sandbox(tmp_path, _state_text()); init_repo(box)
    A = "okx-engineering-agent"
    _commits(box, [("agent: fix first CI blocker", A)] * 4)
    box.run("Enforce same-failure limit", EVENT_NAME="workflow_dispatch", BLOCKER_SIG="none")
    assert box.env["AGENT_LIMIT_REACHED"] == "false"


def test_persist_marks_failed_steps_as_blocked_not_active(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    box.run("Persist agent state and report", PUBLISH_OUTCOME="failure", VALIDATION="success")
    s = box.state()
    assert s["status"] == "BLOCKED" and s["last_blocker"] == "failed:publish" and s["same_failure_attempts"] == "1"


def test_persist_records_policy_rejection_and_counts_it(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    box.run("Persist agent state and report", POLICY_REJECTED="true", POLICY_REASON="denied-path")
    assert box.state()["last_blocker"] == "policy:denied-path" and box.state()["status"] == "BLOCKED"
    report = (box.dir / "agent" / "REPORT.md").read_text()
    assert "Change policy: denied-path" in report and "rejected by policy" in report
    box.env.update({"PREV_SIG": "policy:denied-path", "PREV_ATTEMPTS": "1"})
    box.run("Persist agent state and report", POLICY_REJECTED="true", POLICY_REASON="denied-path")
    assert box.state()["same_failure_attempts"] == "2"


def test_persist_report_flags_safety_critical_review(tmp_path):
    box = Sandbox(tmp_path, _state_text())
    box.run("Persist agent state and report", POLICY_REVIEW="true")
    assert "human review required" in (box.dir / "agent" / "REPORT.md").read_text()


def _git_shim(box):
    log = box.dir / "git.log"
    shim = box.dir / "bin" / "git"
    shim.write_text(f'#!/bin/bash\necho "$@" >> {log}\nif [ "$1" = "diff" ]; then exit 1; fi\nexit 0\n')
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return log


def test_persist_never_pushes_to_the_default_branch(tmp_path):
    box = Sandbox(tmp_path, _state_text()); log = _git_shim(box)
    box.run("Persist agent state and report", PUSH_TOKEN="tok", HEAD_BRANCH="main")
    assert not log.exists() or "push" not in log.read_text()


def test_persist_still_pushes_feature_branches_when_token_exists(tmp_path):
    box = Sandbox(tmp_path, _state_text()); log = _git_shim(box)
    box.run("Persist agent state and report", PUSH_TOKEN="tok", HEAD_BRANCH="fix/x")
    assert "push origin HEAD:fix/x" in log.read_text()
    assert "github.com/o/r.git" in log.read_text()          # repository comes from the environment


def test_publish_refuses_the_default_branch():
    run = _steps()["Publish normal agent change"]["run"]
    assert 'HEAD_BRANCH" = "${DEFAULT_BRANCH' in run and "git add -A -- . ':!agent/runtime'" in run
