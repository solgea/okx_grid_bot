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
        }
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
                 "Validate agent result"]:
        assert "env.AGENT_LIMIT_REACHED != 'true'" in steps[name]["if"], name
    assert "steps.validate.outputs.changed == 'true'" in steps["Publish normal agent change"]["if"]


def test_agent_cannot_rewrite_its_own_counter():
    assert "git checkout -- agent/STATE.md agent/REPORT.md" in _steps()["Validate agent result"]["run"]
