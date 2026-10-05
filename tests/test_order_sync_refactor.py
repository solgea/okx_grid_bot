from decimal import Decimal
from types import SimpleNamespace

from engine.sync_engine import _is_entry_intent, _sanitize_cl_ord_id


def make_intent(side: str, position_side: str, reduce_only: bool = False):
    return SimpleNamespace(
        side=SimpleNamespace(value=side),
        position_side=position_side,
        reduce_only=reduce_only,
    )


def test_client_order_id_is_normalized_and_bounded():
    assert _sanitize_cl_ord_id("grid-01/A") == "grid01A"
    assert len(_sanitize_cl_ord_id("x" * 40)) == 32
    assert _sanitize_cl_ord_id("---") is None


def test_entry_detection_preserves_hedged_and_net_rules():
    assert _is_entry_intent(make_intent("buy", "long"))
    assert _is_entry_intent(make_intent("sell", "short"))
    assert _is_entry_intent(make_intent("buy", "net"))
    assert not _is_entry_intent(make_intent("sell", "net"))
    assert not _is_entry_intent(make_intent("buy", "net", reduce_only=True))


def test_entry_detection_rejects_unknown_position_mode():
    assert not _is_entry_intent(make_intent("buy", "unknown"))
