import pytest
import time
from decimal import Decimal

from preflight_layer.domain import (
    OrderIntent, 
    OrderSide, 
    OrderType, 
    InstrumentMetadata, 
    AccountState, 
    MarketData, 
    PreFlightState
)
from preflight_layer import codes
from preflight_layer.validator import PreFlightValidator
from preflight_layer.interfaces import IRiskManager


class AsyncWebSocketAdapter:
    """Expose the most recent exchange snapshot through async adapter methods."""

    def __init__(self, snapshots, account, metadata):
        self.snapshots = snapshots
        self.account = account
        self.metadata = metadata
        self.latest_market = None

    async def fetch_instrument_metadata(self, instrument_id):
        return self.metadata

    async def fetch_account_state(self):
        return self.account

    async def fetch_market_data(self, instrument_id):
        async for snapshot in self._websocket_stream():
            self.latest_market = snapshot
        return MarketData(
            bid=Decimal(self.latest_market["bidPx"]),
            ask=Decimal(self.latest_market["askPx"]),
            last=Decimal(self.latest_market["last"]),
            timestamp=self.latest_market["ts"] / 1000,
        )

    async def _websocket_stream(self):
        for snapshot in self.snapshots:
            yield snapshot


class MockRiskManager(IRiskManager):
    def is_kill_switch_active(self) -> bool: return False
    def is_trading_halted(self) -> bool: return False
    def validate_position_limits(self, account, intent) -> bool: return True
    def validate_risk(self, account, intent) -> bool: return True  


class RejectingRiskManager(MockRiskManager):
    def validate_risk(self, account, intent) -> bool: return False

@pytest.fixture
def validator():
    return PreFlightValidator(risk_manager=MockRiskManager())

@pytest.fixture
def valid_metadata():
    return InstrumentMetadata(
        symbol="TEST-USDT",
        min_size=Decimal('0.01'),
        tick_size=Decimal('0.1'),
        lot_size=Decimal('0.01'),
        contract_val=Decimal('1.0'),
        is_live=True
    )

@pytest.fixture
def valid_intent():
    # DÜZELTME: symbol yerine instrument_id kullanıldı
    return OrderIntent(
        instrument_id="TEST-USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal('10.5'),
        size=Decimal('0.05'),
        leverage=Decimal('5.0'),
        margin_mode="cross",
        position_side="long",
        reduce_only=False,
        client_order_id="123"
    )

def test_valid_order_passes(validator, valid_intent, valid_metadata):
    account = AccountState(
        balance=Decimal('1000'), 
        available_margin=Decimal('1000'), 
        leverage=Decimal('10')
    )
    
    market = MarketData(
        bid=Decimal('10.4'), 
        ask=Decimal('10.6'), 
        last=Decimal('10.5'), 
        timestamp=time.time()
    )
    
    result = validator.validate(valid_intent, valid_metadata, account, market)
    assert result.passed == True
    assert validator.state == PreFlightState.AUTHORIZED

def test_quantity_below_min_rejected(validator, valid_intent, valid_metadata):
    valid_intent.size = Decimal('0.005')
    
    account = AccountState(
        balance=Decimal('1000'), 
        available_margin=Decimal('1000'), 
        leverage=Decimal('10')
    )
    
    market = MarketData(
        bid=Decimal('10.4'), 
        ask=Decimal('10.6'), 
        last=Decimal('10.5'), 
        timestamp=time.time()
    )
    
    result = validator.validate(valid_intent, valid_metadata, account, market)
    assert result.passed == False
    assert result.rejection_code == "PF010_QUANTITY_BELOW_MIN"


def test_max_position_size_rejected(valid_intent, valid_metadata):
    valid_intent.size = Decimal("0.11")

    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("10"),
    )
    market = MarketData(
        bid=Decimal("10.4"),
        ask=Decimal("10.6"),
        last=Decimal("10.5"),
        timestamp=time.time(),
    )

    result = PreFlightValidator().validate(valid_intent, valid_metadata, account, market)

    assert result.passed is False
    assert result.rejection_code == "PF018_MAX_SIZE_EXCEEDED"
    assert result.message == "Order size 0.11 exceeds maximum 0.1."


def test_risk_manager_rejection_is_not_bypassed(valid_intent, valid_metadata):
    validator = PreFlightValidator(risk_manager=RejectingRiskManager())
    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("10"),
    )
    market = MarketData(
        bid=Decimal("10.4"),
        ask=Decimal("10.6"),
        last=Decimal("10.5"),
        timestamp=time.time(),
    )

    result = validator.validate(valid_intent, valid_metadata, account, market)

    assert result.passed is False
    assert result.rejection_code == "RISK_VALIDATION_FAILED"
    assert validator.state == PreFlightState.REJECTED


@pytest.mark.asyncio
async def test_order_manager_uses_latest_async_websocket_market_snapshot(
    validator, valid_intent, valid_metadata
):
    from preflight_layer.domain import AccountState
    from preflight_layer.order_manager import OrderManager

    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("10"),
    )
    current_time_ms = int(time.time() * 1000)
    adapter = AsyncWebSocketAdapter(
        snapshots=[
            {"bidPx": "10.3", "askPx": "10.5", "last": "10.4", "ts": current_time_ms - 1000},
            {"bidPx": "10.4", "askPx": "10.6", "last": "10.5", "ts": current_time_ms},
        ],
        account=account,
        metadata=valid_metadata,
    )

    accepted = await OrderManager(adapter, validator).execute_intent(valid_intent)

    assert accepted is True
    assert adapter.latest_market == {
        "bidPx": "10.4",
        "askPx": "10.6",
        "last": "10.5",
        "ts": current_time_ms,
    }
    assert validator.state == PreFlightState.AUTHORIZED


@pytest.mark.asyncio
async def test_order_manager_rejects_order_using_async_metadata_update(
    validator, valid_intent, valid_metadata
):
    from preflight_layer.domain import AccountState
    from preflight_layer.order_manager import OrderManager

    valid_intent.size = Decimal("1.0")
    updated_metadata = InstrumentMetadata(
        symbol=valid_metadata.symbol,
        min_size=Decimal("2.0"),
        tick_size=valid_metadata.tick_size,
        lot_size=valid_metadata.lot_size,
        contract_val=valid_metadata.contract_val,
        is_live=valid_metadata.is_live,
    )
    adapter = AsyncWebSocketAdapter(
        snapshots=[
            {"bidPx": "10.4", "askPx": "10.6", "last": "10.5", "ts": 1_700_000_001_000}
        ],
        account=AccountState(
            balance=Decimal("1000"),
            available_margin=Decimal("1000"),
            leverage=Decimal("10"),
        ),
        metadata=updated_metadata,
    )

    accepted = await OrderManager(adapter, validator).execute_intent(valid_intent)

    assert accepted is False
    assert validator.state == PreFlightState.REJECTED