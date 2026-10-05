from decimal import Decimal
import pytest

from strategy.grid_engine import GridEngine


def test_grid_calculation_uses_decimal_values():
    engine = GridEngine(
        lower_price="100.01",
        upper_price="100.09",
        grid_count=5,
        contract_size="0.01",
        price_precision=4,
    )

    assert isinstance(engine.lower_price, Decimal)
    assert isinstance(engine.upper_price, Decimal)
    assert isinstance(engine.grid_step, Decimal)
    assert all(isinstance(level, Decimal) for level in engine.grid_levels)


def test_decimal_conversion_avoids_binary_float_artifacts():
    engine = GridEngine(0, 1, 2, contract_size=0.1, price_precision=8)

    value = engine._decimal(0.1)
    assert value == Decimal("0.1")
    assert str(value) == "0.1"


def test_non_finite_numeric_input_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        GridEngine(float("nan"), 100, 5, 0.1)

    with pytest.raises(ValueError, match="finite"):
        GridEngine(100, float("inf"), 5, 0.1)


def test_price_quantization_is_deterministic():
    engine = GridEngine(100, 100.03, 4, 0.1, price_precision=2)

    assert engine.grid_levels == [
        Decimal("100.00"),
        Decimal("100.01"),
        Decimal("100.02"),
        Decimal("100.03"),
    ]


def test_size_quantization_is_round_down_and_decimal():
    engine = GridEngine(100, 200, 5, 0.1)

    assert engine._quantize_size(Decimal("0.123456789")) == Decimal("0.12345678")
