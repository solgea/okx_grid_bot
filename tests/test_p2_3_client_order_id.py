import hashlib

from engine.sync_engine import _sanitize_cl_ord_id


def test_valid_short_client_order_id_is_preserved():
    assert _sanitize_cl_ord_id("gridABC123") == "gridABC123"


def test_sanitization_is_deterministic():
    value = _sanitize_cl_ord_id("grid-ABC/123")
    assert value == _sanitize_cl_ord_id("grid-ABC/123")
    assert value.isalnum()
    assert len(value) <= 32


def test_distinct_ids_that_sanitize_to_same_prefix_do_not_collide():
    first = _sanitize_cl_ord_id("prefix-" + "A" * 40)
    second = _sanitize_cl_ord_id("prefix_" + "A" * 40)

    assert first != second
    assert len(first) <= 32
    assert len(second) <= 32


def test_long_ids_with_same_first_32_chars_do_not_collide():
    first = _sanitize_cl_ord_id("X" * 32 + "-one")
    second = _sanitize_cl_ord_id("X" * 32 + "-two")

    assert first != second
    assert len(first) == 31
    assert len(second) == 31


def test_empty_or_non_alphanumeric_only_id_is_rejected():
    assert _sanitize_cl_ord_id("") is None
    assert _sanitize_cl_ord_id("---") is None
