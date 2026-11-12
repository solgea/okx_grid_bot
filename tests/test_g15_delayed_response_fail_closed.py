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



@pytest.mark.asyncio
async def test_timeout_processor_uses_explicit_phase_a_shadow_quantity():
    from demo_exec.executor import SHADOW_ORDER_QUANTITY

    executor = DemoExecutor(TimeoutNullTransport())
    intent = Intent.create("g15agent", "ETH/USDT:USDT", "buy", "shadow quantity", 11)
    result = await executor.submit(intent)

    assert result.state == LifecycleState.UNKNOWN.value
    assert executor._order_events[result.client_order_id].order_quantity == SHADOW_ORDER_QUANTITY
    assert SHADOW_ORDER_QUANTITY == Decimal("1")


@pytest.mark.asyncio
async def test_unknown_fill_progress_is_journaled_and_never_regresses(tmp_path):
    journal_path = tmp_path / "unknown-progress.jsonl"
    journal = Journal(journal_path)
    executor = DemoExecutor(TimeoutNullTransport(), journal=journal)
    intent = Intent.create("g15agent", "ETH/USDT:USDT", "buy", "unknown progress", 12)
    result = await executor.submit(intent)
    cl_id = result.client_order_id

    newer_unknown = OrderEvent("unknown-fill-newer", LifecycleState.UNKNOWN, Decimal("0.6"))
    assert executor.handle_order_event(cl_id, newer_unknown) is True
    assert executor._order_events[cl_id].cumulative_filled == Decimal("0.6")

    older_unknown = OrderEvent("unknown-fill-older", LifecycleState.UNKNOWN, Decimal("0.2"))
    assert executor.handle_order_event(cl_id, older_unknown) is False
    assert executor._order_events[cl_id].cumulative_filled == Decimal("0.6")

    # A stale authoritative partial event must not resolve UNKNOWN or roll back fills.
    stale_partial = OrderEvent("stale-partial", LifecycleState.PARTIAL, Decimal("0.4"))
    assert executor.handle_order_event(cl_id, stale_partial) is False
    processor = executor._order_events[cl_id]
    assert processor.lifecycle.state is LifecycleState.UNKNOWN
    assert processor.cumulative_filled == Decimal("0.6")

    rows = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["INTENT", "UNKNOWN", "ORDER_EVENT"]
    assert rows[-1]["state"] == LifecycleState.UNKNOWN.value
    assert rows[-1]["cumulative_filled"] == "0.6"


@pytest.mark.asyncio
async def test_late_partial_then_filled_after_timeout_is_monotonic():
    executor = DemoExecutor(TimeoutNullTransport())
    result = await executor.submit(
        Intent.create("g15agent", "ETH/USDT:USDT", "buy", "late partial", 13)
    )
    cl_id = result.client_order_id

    assert executor.handle_order_event(
        cl_id, OrderEvent("late-partial-1", LifecycleState.PARTIAL, Decimal("0.4"))
    ) is True
    assert executor._order_events[cl_id].cumulative_filled == Decimal("0.4")

    assert executor.handle_order_event(
        cl_id, OrderEvent("late-filled-1", LifecycleState.FILLED, Decimal("1"))
    ) is True
    assert executor._order_events[cl_id].lifecycle.state is LifecycleState.FILLED
    assert executor._order_events[cl_id].cumulative_filled == Decimal("1")

    # A late, lower fill notification is stale and cannot regress terminal state.
    assert executor.handle_order_event(
        cl_id, OrderEvent("late-partial-old", LifecycleState.PARTIAL, Decimal("0.7"))
    ) is False
    assert executor._order_events[cl_id].lifecycle.state is LifecycleState.FILLED
    assert executor._order_events[cl_id].cumulative_filled == Decimal("1")
