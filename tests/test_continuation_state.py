from __future__ import annotations

import copy
import json

import pytest

from automation.continuation_state import (
    SCHEMA, load_state, save_state, transition_state, validate_state,
)


def state(**overrides):
    value = {
        "schema": SCHEMA,
        "task_id": "free-llmapi-audit",
        "status": "READY",
        "checkpoint_sha": "78be59a2d642debe81b9eee43fea50a6b5e93b57",
        "next_step": "Review API smoke configuration",
        "attempts": 0,
        "updated_at_utc": "2026-10-14T19:00:00+00:00",
        "resume_after_utc": None,
        "reason_code": None,
    }
    value.update(overrides)
    return value


def test_checkpoint_round_trip_is_atomic_and_validated(tmp_path):
    path = tmp_path / "state" / "checkpoint.json"
    save_state(path, state())
    assert load_state(path) == state()
    assert list(path.parent.glob("*.tmp")) == []


def test_unknown_fields_are_rejected_so_secrets_cannot_be_persisted():
    value = state(api_key="should-never-be-stored")
    with pytest.raises(ValueError, match="fields mismatch"):
        validate_state(value)


def test_waiting_for_quota_requires_resume_time():
    with pytest.raises(ValueError, match="requires resume_after_utc"):
        validate_state(state(status="WAITING_FOR_QUOTA"))


def test_quota_wait_cannot_resume_automatically_via_state_transition():
    waiting = state(status="WAITING_FOR_QUOTA", resume_after_utc="2026-10-15T00:00:00+00:00", reason_code="RATE_LIMIT")
    with pytest.raises(ValueError, match="transition not allowed"):
        transition_state(waiting, "READY")


def test_run_attempt_increments_only_when_entering_running():
    running = transition_state(state(), "RUNNING", now_utc="2026-10-14T19:01:00+00:00")
    assert running["attempts"] == 1
    ready = transition_state(running, "READY", now_utc="2026-10-14T19:02:00+00:00")
    assert ready["attempts"] == 1


def test_completed_task_is_terminal():
    completed = state(status="COMPLETED")
    with pytest.raises(ValueError, match="transition not allowed"):
        transition_state(completed, "READY")


def test_invalid_json_fails_closed(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_state(path)


def test_non_utc_timestamp_is_rejected():
    with pytest.raises(ValueError, match="must be UTC"):
        validate_state(state(updated_at_utc="2026-10-14T22:00:00+03:00"))
