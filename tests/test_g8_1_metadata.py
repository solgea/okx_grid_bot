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

def test_g8_1_rejects_instrument_identity_mismatch():
    metadata = InstrumentMetadata(symbol="ETH/USDT:USDT", min_size=Decimal("0.01"), tick_size=Decimal("0.1"), lot_size=Decimal("0.01"), contract_val=Decimal("0.01"), is_live=True)
    result = PreFlightValidator().validate(intent(), metadata, account(), market())
    assert not result.passed
    assert result.rejection_code == "PF001_INVALID_INSTRUMENT"

def test_g8_1_rejects_invalid_exchange_metadata():
    metadata = InstrumentMetadata(symbol="BTC/USDT:USDT", min_size=Decimal("0.01"), tick_size=Decimal("0"), lot_size=Decimal("0.01"), contract_val=Decimal("0.01"), is_live=True)
    result = PreFlightValidator().validate(intent(), metadata, account(), market())
    assert not result.passed
    assert result.rejection_code == "PF004_INVALID_TICK_SIZE"
