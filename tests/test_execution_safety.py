from decimal import Decimal
import time

from preflight_layer.domain import AccountState, InstrumentMetadata, MarketData, OrderIntent, OrderSide, OrderType
from preflight_layer.validator import PreFlightValidator
from engine.risk_manager import RiskManager


def metadata():
    return InstrumentMetadata(
        symbol="BTC/USDT:USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.1"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("0.01"),
        is_live=True,
    )


def account():
    return AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("3"),
    )


def market():
    return MarketData(
        bid=Decimal("60000"),
        ask=Decimal("60000"),
        last=Decimal("60000"),
        timestamp=time.time(),
    )


def intent(price="60000.0", size="0.01", leverage="3"):
    return OrderIntent(
        instrument_id="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal(price),
        size=Decimal(size),
        leverage=Decimal(leverage),
        margin_mode="cross",
        position_side="net",
        reduce_only=False,
        client_order_id="test-safety",
    )


def test_preflight_accepts_aligned_order(monkeypatch):
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    result = PreFlightValidator().validate(intent(), metadata(), account(), market())
    assert result.passed


def test_preflight_rejects_tick_mismatch(monkeypatch):
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    result = PreFlightValidator().validate(intent(price="60000.05"), metadata(), account(), market())
    assert not result.passed
    assert result.rejection_code == "PF008_PRICE_TICK_MISMATCH"


def test_preflight_rejects_stale_market():
    stale = market()
    stale.timestamp = time.time() - 120
    result = PreFlightValidator().validate(intent(), metadata(), account(), stale)
    assert not result.passed
    assert result.rejection_code == "PF025_STALE_MARKET_DATA"


def test_risk_manager_hard_limits_absolute_position_size():
    rm = RiskManager()
    rm.initialize_balance(1000)
    assert rm.check_risk_limits(1000, 0.11)
