"""Strict checkpoint state for resumable, non-trading engineering tasks.

This module stores task metadata only. It intentionally has no prompt, credential,
exchange, git-write, or model-client fields.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "engineering-continuation.v1"
STATUSES = {"READY", "RUNNING", "WAITING_FOR_QUOTA", "BLOCKED", "COMPLETED", "FAILED"}
_FIELDS = {
    "schema", "task_id", "status", "checkpoint_sha", "next_step", "attempts",
    "updated_at_utc", "resume_after_utc", "reason_code",
}
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_REASON = re.compile(r"^[A-Z0-9_]{1,48}$")
_TRANSITIONS = {
    "READY": {"RUNNING", "BLOCKED"},
    "RUNNING": {"READY", "WAITING_FOR_QUOTA", "BLOCKED", "COMPLETED", "FAILED"},
    "WAITING_FOR_QUOTA": {"BLOCKED"},
    "BLOCKED": {"READY"},
    "COMPLETED": set(),
    "FAILED": {"READY", "BLOCKED"},
}


def _utc_timestamp(value: Any, field: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field} must be UTC")


def validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("checkpoint must be a JSON object")
    if set(state) != _FIELDS:
        missing = sorted(_FIELDS - set(state))
        extra = sorted(set(state) - _FIELDS)
        raise ValueError(f"checkpoint fields mismatch; missing={missing}, extra={extra}")
    if state["schema"] != SCHEMA:
        raise ValueError("unsupported checkpoint schema")
    if not isinstance(state["task_id"], str) or not _TASK_ID.fullmatch(state["task_id"]):
        raise ValueError("invalid task_id")
    if state["status"] not in STATUSES:
        raise ValueError("invalid status")
    sha = state["checkpoint_sha"]
    if sha is not None and (not isinstance(sha, str) or not _SHA.fullmatch(sha)):
        raise ValueError("checkpoint_sha must be null or a full lowercase Git SHA")
    if not isinstance(state["next_step"], str) or not state["next_step"] or len(state["next_step"]) > 240:
        raise ValueError("next_step must be a non-empty description of at most 240 characters")
    if isinstance(state["attempts"], bool) or not isinstance(state["attempts"], int) or state["attempts"] < 0:
        raise ValueError("attempts must be a non-negative integer")
    _utc_timestamp(state["updated_at_utc"], "updated_at_utc")
    _utc_timestamp(state["resume_after_utc"], "resume_after_utc", optional=True)
    reason = state["reason_code"]
    if reason is not None and (not isinstance(reason, str) or not _REASON.fullmatch(reason)):
        raise ValueError("reason_code must be null or an uppercase machine-readable code")
    if state["status"] == "WAITING_FOR_QUOTA" and state["resume_after_utc"] is None:
        raise ValueError("WAITING_FOR_QUOTA requires resume_after_utc")
    if state["status"] != "WAITING_FOR_QUOTA" and state["resume_after_utc"] is not None:
        raise ValueError("resume_after_utc is only valid while WAITING_FOR_QUOTA")
    return dict(state)


def transition_state(state: dict[str, Any], target: str, *, now_utc: str | None = None,
                     resume_after_utc: str | None = None, reason_code: str | None = None,
                     manual_resume: bool = False) -> dict[str, Any]:
    current = validate_state(state)
    if target not in _TRANSITIONS[current["status"]]:
        raise ValueError(f"transition not allowed: {current['status']} -> {target}")
    if current["status"] == "WAITING_FOR_QUOTA" and target == "BLOCKED" and not manual_resume:
        raise ValueError("quota-waiting task requires explicit manual review before blocking")
    stamp = now_utc or datetime.now(timezone.utc).isoformat()
    next_state = {**current, "status": target, "updated_at_utc": stamp,
                  "resume_after_utc": resume_after_utc if target == "WAITING_FOR_QUOTA" else None,
                  "reason_code": reason_code}
    next_state["attempts"] = current["attempts"] + (1 if target == "RUNNING" else 0)
    return validate_state(next_state)


def load_state(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("checkpoint missing or invalid JSON") from exc
    return validate_state(raw)


def save_state(path: str | Path, state: dict[str, Any]) -> None:
    """Atomically persist a validated, secret-free checkpoint."""
    clean = validate_state(state)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(clean, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
