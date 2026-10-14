from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from demo_exec.executor import DemoExecutor
from demo_exec.intent import Intent
from demo_exec.journal import Journal
from demo_exec.transport import NullTransport

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "artifacts" / "phase_a"
SYMBOL = os.getenv("PHASE_A_SYMBOL", "ETH/USDT:USDT")


def acceptance_passes(acceptance: dict[str, Any]) -> bool:
    """Validate Phase-A booleans and zero-valued safety counters explicitly."""
    return (
        acceptance.get("daily_shadow_run") is True
        and acceptance.get("null_transport_only") is True
        and acceptance.get("unexpected_exchange_order_calls") == 0
        and acceptance.get("unresolved_incidents") == 0
    )


def phase_a_agent_id(day: str, run_id: str = "local") -> str:
    """Return a run-scoped synthetic ID; this is not a persistent trading agent."""
    safe_run_id = re.sub(r"[^A-Za-z0-9]", "", str(run_id)) or "local"
    return f"phasea{day.replace('-', '')}{safe_run_id}"


def phase_a_evidence_filename(day: str, run_id: str, attempt: str) -> str:
    """Build a unique, immutable evidence filename for one workflow attempt."""
    safe_run_id = re.sub(r"[^A-Za-z0-9_-]", "", str(run_id))
    safe_attempt = re.sub(r"[^A-Za-z0-9_-]", "", str(attempt))
    if not safe_run_id or not safe_attempt:
        raise ValueError("Phase-A run ID and attempt must be non-empty")
    return f"{day}-run-{safe_run_id}-attempt-{safe_attempt}.json"


def validate_evidence_consistency(
    evidence: dict[str, Any],
    expected_provenance: dict[str, str] | None = None,
) -> bool:
    """Reject inconsistent counts and, when supplied, mismatched runtime provenance."""
    event = evidence.get("workflow_event")
    run_id = evidence.get("workflow_run_id")
    attempt = evidence.get("workflow_run_attempt")
    git_sha = evidence.get("git_sha")
    day = evidence.get("date_utc")

    if event in ("schedule", "workflow_dispatch"):
        provenance_valid = (
            run_id not in (None, "", "local")
            and attempt not in (None, "", "local")
            and isinstance(git_sha, str)
            and bool(re.fullmatch(r"[0-9a-f]{40}", git_sha))
            and evidence.get("evidence_id")
            == phase_a_evidence_filename(day, str(run_id), str(attempt))
        )
    elif event == "local":
        provenance_valid = (
            run_id == "local"
            and attempt == "local"
            and git_sha == "local"
            and evidence.get("evidence_id")
            == phase_a_evidence_filename(day, "local", "local")
        )
    else:
        provenance_valid = False

    if expected_provenance is not None:
        provenance_valid = provenance_valid and all(
            evidence.get(field) == expected_provenance.get(field)
            for field in ("git_sha", "workflow_run_id", "workflow_run_attempt", "workflow_event")
        )

    return (
        evidence.get("schema") == "phase-a-evidence.v3"
        and evidence.get("transport") == "NullTransport"
        and evidence.get("intent_count") == evidence.get("null_transport_place_calls")
        and evidence.get("intent_count") == evidence.get("journal_event_count")
        and provenance_valid
        and evidence.get("sequence_scope") == "daily_synthetic_validation"
        and evidence.get("sequence_continuity_proven") is False
        and evidence.get("exchange_touched") is False
        and evidence.get("exchange_mutation_calls") == 0
        and evidence.get("exchange_order_call_observation", {}).get("value") == 0
        and evidence.get("acceptance", {}).get("unexpected_exchange_order_calls") == 0
        and evidence.get("incidents") == []
        and acceptance_passes(evidence.get("acceptance", {}))
    )


async def run_shadow() -> dict:
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    run_id = os.getenv("GITHUB_RUN_ID", "local")
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "local")
    event = os.getenv("GITHUB_EVENT_NAME", "local")
    git_sha = os.getenv("GITHUB_SHA", "local")
    expected_provenance = {
        "git_sha": git_sha,
        "workflow_run_id": run_id,
        "workflow_run_attempt": attempt,
        "workflow_event": event,
    }
    evidence_id = phase_a_evidence_filename(day, run_id, attempt)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / evidence_id
    if path.exists():
        raise RuntimeError(f"E_EVIDENCE_EXISTS: {path}")

    # This temporary journal validates this run only; it is not the durable
    # production journal and cannot prove cross-run sequence continuity.
    journal_path = EVIDENCE_DIR / f".{day}-{run_id}-{attempt}.jsonl"
    transport = NullTransport()
    journal = Journal(journal_path)
    executor = DemoExecutor(transport, demo_phase="A", enabled=True, journal=journal)
    agent_id = phase_a_agent_id(day, run_id)

    try:
        results = []
        for seq in (1, 2, 3):
            intent = Intent.create(agent_id, SYMBOL, "buy", "daily-shadow-validation", seq)
            result = await executor.submit(intent)
            results.append({
                "seq": seq,
                "accepted": result.accepted,
                "code": result.code,
                "state": result.state,
                "client_order_id": result.client_order_id,
            })

        rows = journal.read()
        counts_consistent = len(results) == transport.place_calls == len(rows)
        evidence = {
            "schema": "phase-a-evidence.v3",
            "evidence_id": evidence_id,
            "date_utc": day,
            "recorded_at_utc": now.isoformat(),
            **expected_provenance,
            "phase": "A",
            "symbol": SYMBOL,
            "transport": type(transport).__name__,
            "exchange_touched": False,
            "exchange_mutation_calls": 0,
            "exchange_order_call_observation": {
                "value": 0,
                "basis": "structural",
                "details": (
                    "DemoExecutor accepts only NullTransport in Phase A; NullTransport "
                    "has no exchange client. This is a structural guarantee, not external "
                    "network telemetry."
                ),
            },
            "null_transport_place_calls": transport.place_calls,
            "intent_count": len(results),
            "journal_event_count": len(rows),
            "counts_consistent": counts_consistent,
            "agent_id": agent_id,
            "sequence_scope": "daily_synthetic_validation",
            "sequence_continuity_proven": False,
            "results": results,
            "incidents": [],
            "acceptance": {
                "daily_shadow_run": all(r["accepted"] and r["code"] == "SHADOW" for r in results),
                "null_transport_only": isinstance(transport, NullTransport) and counts_consistent,
                "unexpected_exchange_order_calls": 0,
                "unresolved_incidents": 0,
            },
        }

        if not validate_evidence_consistency(evidence, expected_provenance):
            raise RuntimeError("E_PHASE_A_DAILY_GATE")

        # Exclusive creation protects immutable evidence from accidental overwrite.
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        return evidence
    finally:
        journal_path.unlink(missing_ok=True)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_shadow()), indent=2, sort_keys=True))
