from decimal import Decimal
import time
from preflight_layer.domain import AccountState, InstrumentMetadata, MarketData, OrderIntent, OrderSide, OrderType
from preflight_layer.validator import PreFlightValidator

def account():
    return AccountState(balance=Decimal("1000"), available_margin=Decimal("1000"), leverage=Decimal("3"))

def market():
    return MarketData(bid=Decimal("60000"), ask=Decimal("60000"), last=Decimal("60000"), timestamp=time.time())

def intent(price="60000", size="0.01", leverage="3"):
    return OrderIntent(
        instrument_id="BTC/USDT:USDT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
        price=Decimal(price), size=Decimal(size), leverage=Decimal(leverage),
        margin_mode="cross", position_side="net", reduce_only=False, client_order_id="g8"
    )

def metadata():
    return InstrumentMetadata(symbol="BTC/USDT:USDT", min_size=Decimal("0.01"), tick_size=Decimal("0.1"), lot_size=Decimal("0.01"), contract_val=Decimal("0.01"), is_live=True)

def test_g8_2_rejects_quantity_above_position_limit(monkeypatch):
    monkeypatch.setattr("config.settings.config.MAX_POSITION_SIZE", 0.1)
    result = PreFlightValidator().validate(intent(size="0.11"), metadata(), account(), market())
    assert not result.passed
    assert result.rejection_code == "PF018_MAX_SIZE_EXCEEDED"

def test_g8_2_rejects_lot_misalignment():
    result = PreFlightValidator().validate(intent(size="0.015"), metadata(), account(), market())
    assert not result.passed
    assert result.rejection_code == "PF011_QUANTITY_LOT_MISMATCH"
