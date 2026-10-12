import ast
import json
from pathlib import Path

import pytest

from demo_exec.lifecycle import Lifecycle, LifecycleState
from demo_exec.journal import Journal
from demo_exec.executor import DemoExecutor
from demo_exec.intent import Intent
from demo_exec.promotion import Promotion, PromotionCheck, PromotionState
from demo_exec.recovery import Recovery
from demo_exec.reconciler import ShadowReconciler
from demo_exec.transport import NullTransport, OkxDemoTransport

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_t01_non_demo_submit_is_rejected_before_transport():
    transport = NullTransport()
    executor = DemoExecutor(transport, is_demo=False)
    intent = Intent.create("agent1", "ETH/USDT:USDT", "buy", "T01 non-demo guard", 1)

    result = await executor.submit(intent)

    assert result.accepted is False
    assert result.code == "E_NOT_DEMO"
    assert transport.place_calls == 0

def test_t02_create_order_only_transport():
    violations = []
    for path in ROOT.rglob("*.py"):
        if ".git" in path.parts or "__pycache__" in path.parts or "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_order":
                if path.relative_to(ROOT).as_posix() != "demo_exec/transport.py" and path.relative_to(ROOT).as_posix() != "demo_trading.py":
                    violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []

def test_t03_phase_a_rejects_real_transport():
    with pytest.raises(RuntimeError, match="E_PHASE_LOCK"):
        OkxDemoTransport(object(), demo_phase="A", is_demo=True)


@pytest.mark.asyncio
async def test_t06_journal_prevents_seq_reuse_after_restart(tmp_path):
    journal = Journal(tmp_path / "events.jsonl")
    intent = Intent.create("agent1", "ETH/USDT:USDT", "buy", "T06 restart", 7)
    first_transport = NullTransport()
    first = DemoExecutor(first_transport, journal=journal)
    assert (await first.submit(intent)).accepted
    assert first_transport.place_calls == 1

    restarted_transport = NullTransport()
    restarted = DemoExecutor(restarted_transport, journal=journal)
    result = await restarted.submit(intent)
    assert result.code == "E_JOURNAL"
    assert restarted_transport.place_calls == 0


class TimeoutNullTransport(NullTransport):
    async def place(self, intent):
        self.place_calls += 1
        raise TimeoutError("simulated timeout")


@pytest.mark.asyncio
async def test_t07_timeout_records_unknown_and_does_not_retry():
    transport = TimeoutNullTransport()
    executor = DemoExecutor(transport)
    intent = Intent.create("agent1", "ETH/USDT:USDT", "buy", "T07 timeout", 8)

    result = await executor.submit(intent)
    assert result.state == LifecycleState.UNKNOWN.value
    retry = await executor.submit(intent)
    assert retry.code == "E_JOURNAL"
    assert transport.place_calls == 1


@pytest.mark.asyncio
async def test_t08_unresolved_unknown_stops_agent():
    transport = TimeoutNullTransport()
    executor = DemoExecutor(transport)
    first = Intent.create("agent1", "ETH/USDT:USDT", "buy", "T08 timeout", 9)
    second = Intent.create("agent1", "ETH/USDT:USDT", "buy", "T08 blocked follow-up", 10)

    result = await executor.submit(first)
    assert result.state == LifecycleState.UNKNOWN.value
    blocked = await executor.submit(second)
    assert blocked.code == "E_AGENT_STATE"
    assert transport.place_calls == 1

def test_t06_persisted_seq_is_recovered():
    path = ROOT / "tests" / ".tmp-demo-journal.jsonl"
    path.write_text(json.dumps({"seq": 7}) + "\n", encoding="utf-8")
    try:
        result = Recovery().recover(str(path), last_seq=7)
        assert result.state == "RECOVERED_PAUSED"
    finally:
        path.unlink()

def test_t07_timeout_is_unknown_and_not_resubmitted():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.SUBMITTED)
    lifecycle.transition(LifecycleState.UNKNOWN)
    assert lifecycle.state is LifecycleState.UNKNOWN
    with pytest.raises(ValueError):
        lifecycle.transition(LifecycleState.SUBMITTED)

def test_t08_unresolved_unknown_stops_progress():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.SUBMITTED)
    lifecycle.transition(LifecycleState.UNKNOWN)
    with pytest.raises(ValueError):
        lifecycle.transition(LifecycleState.FILLED)

def test_t14_mismatch_stops_without_repair():
    result = ShadowReconciler().reconcile(local_state={"id": "1"}, exchange_state={"id": "2"})
    assert result.code == "E_RECONCILIATION" and result.stopped

def test_t15_unmanaged_order_is_untouched():
    result = ShadowReconciler().reconcile_orders([], [{"id": "foreign", "clientOrderId": "manual123"}])
    assert result.code == "UNMANAGED_ORDERS_IGNORED" and not result.stopped

def test_t23_failed_promotion_stays_paper():
    p = Promotion(4); p.request()
    check = PromotionCheck(True, True, True, True, True, True, True, False)
    assert not p.approve(check) and p.state is PromotionState.PAPER

def test_t24_promotion_preserves_seq():
    p = Promotion(41); p.request()
    check = PromotionCheck(True, True, True, True, True, True, True, True)
    assert p.approve(check) and p.state is PromotionState.DEMO and p.seq == 41

def test_t25_recovery_is_paused():
    path = ROOT / "tests" / ".tmp-recovery.jsonl"
    path.write_text(json.dumps({"seq": 1}) + "\n" + json.dumps({"seq": 2}) + "\n", encoding="utf-8")
    try:
        assert Recovery().recover(str(path)).state == "RECOVERED_PAUSED"
    finally:
        path.unlink()

def test_t26_corrupt_journal_blocks(tmp_path):
    path = tmp_path / "journal.jsonl"; path.write_text("{bad\n", encoding="utf-8")
    result = Recovery().recover(str(path))
    assert result.state == "BLOCKED" and result.reason == "E_JOURNAL_CORRUPT"

def test_t26_seq_gap_blocks(tmp_path):
    path = tmp_path / "journal.jsonl"
    path.write_text(json.dumps({"seq": 1}) + "\n" + json.dumps({"seq": 3}) + "\n", encoding="utf-8")
    result = Recovery().recover(str(path))
    assert result.state == "BLOCKED" and result.reason == "E_SEQ_GAP"


class ConnectionDropNullTransport(NullTransport):
    async def place(self, intent):
        self.place_calls += 1
        raise ConnectionError("simulated connection drop after submit")


@pytest.mark.asyncio
async def test_t27_connection_drop_fails_closed_as_unknown_without_retry():
    transport = ConnectionDropNullTransport()
    executor = DemoExecutor(transport)
    first = Intent.create("agent1", "ETH/USDT:USDT", "buy", "T27 connection drop", 27)

    result = await executor.submit(first)

    assert result.state == LifecycleState.UNKNOWN.value
    retry = await executor.submit(first)
    assert retry.code == "E_JOURNAL"
    assert transport.place_calls == 1


def test_t10_lifecycle_accepts_partial_fill_to_filled():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.SUBMITTED)
    lifecycle.transition(LifecycleState.ACKED)
    lifecycle.transition(LifecycleState.OPEN)
    lifecycle.transition(LifecycleState.PARTIAL)
    lifecycle.transition(LifecycleState.FILLED)
    assert lifecycle.state is LifecycleState.FILLED


def test_t10_lifecycle_rejection_is_terminal():
    lifecycle = Lifecycle()
    lifecycle.transition(LifecycleState.SUBMITTED)
    lifecycle.transition(LifecycleState.REJECTED)
    assert lifecycle.state is LifecycleState.REJECTED
    with pytest.raises(ValueError):
        lifecycle.transition(LifecycleState.SUBMITTED)
