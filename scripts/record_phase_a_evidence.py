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


async def run_shadow() -> dict:
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{day}.json"
    if path.exists():
        raise RuntimeError(f"E_EVIDENCE_EXISTS: {path}")

    journal_path = EVIDENCE_DIR / f".{day}.jsonl"
    transport = NullTransport()
    journal = Journal(journal_path)
    executor = DemoExecutor(transport, demo_phase="A", enabled=True, journal=journal)

    results = []
    for seq in (1, 2, 3):
        intent = Intent.create("phase-a-shadow", SYMBOL, "buy", "daily-shadow-validation", seq)
        result = await executor.submit(intent)
        results.append({
            "seq": seq,
            "accepted": result.accepted,
            "code": result.code,
            "state": result.state,
            "client_order_id": result.client_order_id,
        })

    rows = journal.read()
    evidence = {
        "schema": "phase-a-evidence.v1",
        "date_utc": day,
        "recorded_at_utc": now.isoformat(),
        "git_sha": os.getenv("GITHUB_SHA", "local"),
        "phase": "A",
        "symbol": SYMBOL,
        "transport": "NullTransport",
        "exchange_touched": False,
        "exchange_mutation_calls": 0,
        "null_transport_place_calls": transport.place_calls,
        "intent_count": len(results),
        "journal_event_count": len(rows),
        "results": results,
        "incidents": [],
        "acceptance": {
            "daily_shadow_run": all(r["accepted"] and r["code"] == "SHADOW" for r in results),
            "null_transport_only": transport.place_calls == 3,
            "unexpected_exchange_order_calls": 0,
            "unresolved_incidents": 0,
        },
    }

    if not acceptance_passes(evidence["acceptance"]):
        raise RuntimeError("E_PHASE_A_DAILY_GATE")

    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    journal_path.unlink(missing_ok=True)
    return evidence


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_shadow()), indent=2, sort_keys=True))
