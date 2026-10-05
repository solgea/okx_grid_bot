import ast
import json
from pathlib import Path

import pytest

from demo_exec.lifecycle import Lifecycle, LifecycleState
from demo_exec.promotion import Promotion, PromotionCheck, PromotionState
from demo_exec.recovery import Recovery
from demo_exec.reconciler import ShadowReconciler
from demo_exec.transport import OkxDemoTransport

ROOT = Path(__file__).resolve().parents[1]

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
    with pytest.raises(ValueError, match="Phase A"):
        OkxDemoTransport(object(), demo_phase="A", is_demo=True)

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