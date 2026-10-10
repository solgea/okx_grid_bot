import asyncio

import pytest

from demo_exec.executor import DemoExecutor
from demo_exec.intent import Intent
from demo_exec.lifecycle import Lifecycle, LifecycleState
from demo_exec.journal import Journal
from demo_exec.transport import NullTransport


def intent(seq=1, agent_id="agent1"):
    return Intent.create(agent_id, "ETH/USDT:USDT", "buy", "test", seq)


def test_phase_a_requires_null_transport():
    with pytest.raises(ValueError, match="NullTransport"):
        DemoExecutor(object())


def test_phase_a_rejects_non_a_phase():
    with pytest.raises(ValueError, match="Phase A"):
        DemoExecutor(NullTransport(), demo_phase="B")


@pytest.mark.asyncio
async def test_shadow_submit_never_reaches_exchange():
    transport = NullTransport()
    result = await DemoExecutor(transport).submit(intent())
    assert result.accepted is True
    assert result.code == "SHADOW"
    assert result.state == "SUBMITTED"
    assert transport.place_calls == 1


@pytest.mark.asyncio
async def test_duplicate_agent_seq_is_rejected():
    executor = DemoExecutor(NullTransport())
    assert (await executor.submit(intent(1))).accepted
    second = await executor.submit(intent(1))
    assert second.code == "E_JOURNAL"


@pytest.mark.asyncio
async def test_disabled_shadow_does_not_submit():
    transport = NullTransport()
    result = await DemoExecutor(transport, enabled=False).submit(intent())
    assert result.code == "E_DISABLED"
    assert transport.place_calls == 0


def test_lifecycle_unknown_is_terminal_until_external_resolution():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.SUBMITTED)
    lifecycle.transition(LifecycleState.UNKNOWN)
    with pytest.raises(ValueError):
        lifecycle.transition(LifecycleState.FILLED)


def test_lifecycle_reject_is_not_unknown():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.REJECTED)
    assert lifecycle.state is LifecycleState.REJECTED


def test_write_ahead_journal(tmp_path):
    journal = Journal(tmp_path / "events.jsonl")
    journal.append({"event": "INTENT", "seq": 1})
    journal.append({"event": "SHADOW_SUBMITTED", "seq": 1})
    assert journal.read() == [
        {"event": "INTENT", "seq": 1},
        {"event": "SHADOW_SUBMITTED", "seq": 1},
    ]


def test_clordid_is_bounded_and_alphanumeric():
    result = asyncio.run(DemoExecutor(NullTransport()).submit(intent(12)))
    assert result.client_order_id == "gagent112"
    assert result.client_order_id.isascii()
    assert result.client_order_id.isalnum()
    assert len(result.client_order_id) <= 32


def test_clordid_normalizes_agent_ids_with_punctuation():
    result = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(3, agent_id="phase-a-agent"))
    )
    assert result.client_order_id.isalnum()
    assert len(result.client_order_id) <= 32


def test_clordid_normalization_is_deterministic_across_executors():
    first = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(7, agent_id="phase-a-agent"))
    )
    second = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(7, agent_id="phase-a-agent"))
    )
    assert first.client_order_id == second.client_order_id


def test_clordid_normalizes_long_agent_ids():
    result = asyncio.run(
        DemoExecutor(NullTransport()).submit(intent(8, agent_id="a" * 80))
    )
    assert result.client_order_id.isalnum()
    assert len(result.client_order_id) <= 32
