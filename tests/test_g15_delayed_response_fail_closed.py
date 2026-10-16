from __future__ import annotations

import json
from decimal import Decimal

import pytest

from demo_exec.executor import DemoExecutor
from demo_exec.intent import Intent
from demo_exec.journal import Journal
from demo_exec.lifecycle import LifecycleState
from demo_exec.order_events import OrderEvent
from demo_exec.transport import NullTransport


class TimeoutNullTransport(NullTransport):
    """Simulate an ambiguous submit timeout without network or exchange access."""

    async def place(self, intent: Intent):
        self.place_calls += 1
        raise TimeoutError("simulated ambiguous submit timeout")


@pytest.mark.asyncio
async def test_late_fill_after_submit_timeout_is_recorded_but_new_submits_fail_closed(tmp_path):
    journal_path = tmp_path / "events.jsonl"
    journal = Journal(journal_path)
    transport = TimeoutNullTransport()
    executor = DemoExecutor(transport, journal=journal)
    intent = Intent.create("g15agent", "ETH/USDT:USDT", "buy", "G15 ambiguous submit", 1)

    result = await executor.submit(intent)

    assert result.accepted is False
    assert result.code == "E_TRANSPORT"
    assert result.state == LifecycleState.UNKNOWN.value
    assert result.client_order_id
    assert transport.place_calls == 1

    # An authoritative late fill resolves order reality even while the executor
    # remains stopped for new submissions.
    fill = OrderEvent(
        event_id="late-filled-1",
        state=LifecycleState.FILLED,
        cumulative_filled=Decimal("1"),
    )
    assert executor.handle_order_event(result.client_order_id, fill) is True
    assert executor.handle_order_event(result.client_order_id, fill) is False

    # The ambiguous intent is never retried, and unrelated intents remain blocked.
    same_intent_retry = await executor.submit(intent)
    assert same_intent_retry.accepted is False
    assert same_intent_retry.code == "E_JOURNAL"

    next_intent = Intent.create(
        "g15agent", "ETH/USDT:USDT", "buy", "G15 blocked follow-up", 2
    )
    blocked_intent = await executor.submit(next_intent)
    assert blocked_intent.accepted is False
    assert blocked_intent.code == "E_AGENT_STATE"
    assert transport.place_calls == 1

    rows = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["INTENT", "UNKNOWN", "ORDER_EVENT"]
    assert rows[-1]["state"] == LifecycleState.FILLED.value
    assert rows[-1]["cumulative_filled"] == "1"
