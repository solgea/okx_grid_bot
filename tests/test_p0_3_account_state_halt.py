import pytest

from engine.risk_manager import RiskManager


def test_zero_starting_balance_halts_trading():
    risk = RiskManager()

    with pytest.raises(ValueError, match="positive starting balance"):
        risk.initialize_balance(0.0)

    assert risk.trading_halted is True


def test_positive_starting_balance_does_not_halt():
    risk = RiskManager()
    risk.initialize_balance(1000.0)

    assert risk.trading_halted is False
