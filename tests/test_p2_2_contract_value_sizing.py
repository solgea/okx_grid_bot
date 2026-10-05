from decimal import Decimal
import time
import pytest

from adapters.risk_adapter import RiskPreFlightAdapter
from engine.risk_manager import RiskManager
from preflight_layer.domain import (
    AccountState,
    InstrumentMetadata,
    MarketData,
    OrderIntent,
    OrderSide,
    OrderType,
)
from preflight_layer.validator import PreFlightValidator


def intent(size="1", price="60000"):
    return OrderIntent(
        instrument_id="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal(price),
        size=Decimal(size),
        leverage=Decimal("2"),
    )


def metadata(contract_val="0.01", contract_type="linear"):
    return InstrumentMetadata(
        symbol="BTC/USDT:USDT",
        min_size=Decimal("1"),
        tick_size=Decimal("0.1"),
        lot_size=Decimal("1"),
        contract_val=Decimal(contract_val),
        contract_type=contract_type,
        is_live=True,
    )


def account(margin="1000"):
    return AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal(margin),
        leverage=Decimal("10"),
    )


def test_linear_swap_notional_includes_contract_value():
    risk = RiskManager()
    risk.initialize_balance(1000.0)
    adapter = RiskPreFlightAdapter(risk)

    # 1 contract × 0.01 BTC × 60,000 = 600 USDT notional.
    assert adapter._contract_notional(intent(), metadata()) == Decimal("600.00")


def test_inverse_swap_notional_uses_contract_value_over_price():
    risk = RiskManager()
    risk.initialize_balance(1000.0)
    adapter = RiskPreFlightAdapter(risk)

    # 1 contract × 100 USD / 60,000 = 0.001666... BTC notional.
    value = adapter._contract_notional(intent(), metadata("100", "inverse"))
    assert value == Decimal("100") / Decimal("60000")


def test_preflight_rejects_margin_using_contract_notional(monkeypatch):
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    validator = PreFlightValidator()
    # 100 contracts × 0.01 BTC × 60,000 / 2 = 15,000 USDT margin.
    result = validator.validate(intent(size="100"), metadata(), account("1000"), MarketData(
        last=Decimal("60000"), timestamp=time.time()
    ))
    assert result.passed is False
    assert result.rejection_code == "PF017_INSUFFICIENT_MARGIN"


def test_preflight_accepts_margin_when_contract_value_is_accounted_for(monkeypatch):
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    validator = PreFlightValidator()
    # 1 contract × 0.01 BTC × 60,000 / 2 = 300 USDT margin.
    result = validator.validate(intent(size="1"), metadata(), account("500"), MarketData(
        last=Decimal("60000"), timestamp=time.time()
    ))
    assert result.passed is True


def test_missing_contract_value_fails_closed(monkeypatch):
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    validator = PreFlightValidator()
    result = validator.validate(intent(), metadata("0"), account(), MarketData(
        last=Decimal("60000"), timestamp=time.time()
    ))
    assert result.passed is False
    assert result.rejection_code == "PF013_INVALID_CONTRACT_VALUE"
