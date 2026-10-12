from __future__ import annotations

import asyncio
import json
import os
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


def phase_a_agent_id(day: str) -> str:
    """Return a date-scoped synthetic ID; this is not a persistent trading agent."""
    return f"phasea{day.replace('-', '')}"


def validate_evidence_consistency(evidence: dict[str, Any]) -> bool:
    """Reject evidence whose reported counts or provenance disagree."""
    event = evidence.get("workflow_event")
    return (
        evidence.get("transport") == "NullTransport"
        and evidence.get("intent_count") == evidence.get("null_transport_place_calls")
        and evidence.get("intent_count") == evidence.get("journal_event_count")
        and evidence.get("workflow_run_id") not in (None, "")
        and event in ("schedule", "workflow_dispatch", "local")
        and evidence.get("sequence_scope") == "daily_synthetic_validation"
        and evidence.get("sequence_continuity_proven") is False
        and acceptance_passes(evidence.get("acceptance", {}))
    )


async def run_shadow() -> dict:
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{day}.json"
    if path.exists():
        raise RuntimeError(f"E_EVIDENCE_EXISTS: {path}")

    # This temporary journal validates today's shadow path only. It is not the
    # durable production journal and must not be used to claim cross-day seq continuity.
    journal_path = EVIDENCE_DIR / f".{day}.jsonl"
    transport = NullTransport()
    journal = Journal(journal_path)
    executor = DemoExecutor(transport, demo_phase="A", enabled=True, journal=journal)
    agent_id = phase_a_agent_id(day)

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
        "schema": "phase-a-evidence.v2",
        "date_utc": day,
        "recorded_at_utc": now.isoformat(),
        "git_sha": os.getenv("GITHUB_SHA", "local"),
        "workflow_run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "workflow_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "local"),
        "workflow_event": os.getenv("GITHUB_EVENT_NAME", "local"),
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

    if not validate_evidence_consistency(evidence):
        raise RuntimeError("E_PHASE_A_DAILY_GATE")

    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    journal_path.unlink(missing_ok=True)
    return evidence


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_shadow()), indent=2, sort_keys=True))
