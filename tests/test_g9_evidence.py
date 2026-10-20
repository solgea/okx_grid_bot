"""Validate the committed G9 evidence record.

The contract is explicit: "A successful G9 run must contain a real OKX
Demo `order_id`. CI/test success alone is not G9 PASS." The committed
evidence is therefore checked here so a malformed or regressed record is
caught by CI rather than being trusted on faith.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "artifacts" / "phase_a"
G9_EVIDENCE = EVIDENCE_DIR / "g9-demo-order-2026-10-20.json"

REQUIRED_FIELDS = {
    "cleanup",
    "filled",
    "gate",
    "mode",
    "order_id",
    "position_size",
    "preflight",
    "status",
    "submit_status",
    "symbol",
    "timestamp",
    "verify_error",
}

# cleanup values documented in docs/G9_DEMO_EXECUTION.md
CLEANUP_VALUES = {"CANCELED", "NOT_NEEDED", "FILLED_POSITION_OPEN", "FAILED"}


def test_g9_evidence_is_committed():
    """The real Demo order evidence must exist in the repository."""
    assert G9_EVIDENCE.exists(), f"missing G9 evidence: {G9_EVIDENCE}"


def test_g9_evidence_has_the_documented_shape():
    evidence = json.loads(G9_EVIDENCE.read_text(encoding="utf-8"))

    assert set(evidence) == REQUIRED_FIELDS
    assert evidence["gate"] == "G9"
    assert evidence["mode"] == "DEMO"
    assert evidence["preflight"] == "AUTHORIZED"
    assert evidence["cleanup"] in CLEANUP_VALUES
    assert isinstance(evidence["timestamp"], (int, float))


def test_g9_evidence_contains_a_real_demo_order_id():
    """A real OKX Demo order id is what makes this G9 PASS."""
    evidence = json.loads(G9_EVIDENCE.read_text(encoding="utf-8"))

    order_id = str(evidence["order_id"])
    assert order_id and order_id != "None"
    assert order_id.isdigit(), f"order id is not numeric: {order_id!r}"


def test_g9_evidence_shows_no_open_order_and_no_position():
    """The gate order must be cancelled and must not have left a position."""
    evidence = json.loads(G9_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["status"] == "canceled"
    assert evidence["cleanup"] == "CANCELED"
    assert evidence["filled"] == 0.0
    assert evidence["position_size"] is None
    assert evidence["verify_error"] is None


def test_g9_evidence_timestamp_matches_its_record_date():
    """The file name and the record must agree on the date."""
    from datetime import datetime, timezone

    evidence = json.loads(G9_EVIDENCE.read_text(encoding="utf-8"))

    recorded = datetime.fromtimestamp(
        float(evidence["timestamp"]), tz=timezone.utc
    ).date().isoformat()

    assert recorded in G9_EVIDENCE.name


@pytest.mark.parametrize(
    "name",
    [
        "2026-10-10.json",
        "2026-10-11.json",
        "2026-10-12.json",
    ],
)
def test_daily_shadow_evidence_still_reports_zero_exchange_calls(name):
    """The daily shadow records must keep proving the Phase-A guarantees."""
    evidence = json.loads((EVIDENCE_DIR / name).read_text(encoding="utf-8"))
    acceptance = evidence["acceptance"]

    assert acceptance["daily_shadow_run"] is True
    assert acceptance["null_transport_only"] is True
    assert acceptance["unexpected_exchange_order_calls"] == 0
    assert acceptance["unresolved_incidents"] == 0
    assert evidence["exchange_touched"] is False
    assert evidence["incidents"] == []
