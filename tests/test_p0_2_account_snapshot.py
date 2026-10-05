from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from config.settings import config
from engine.sync_engine import OrderSyncEngine
from preflight_layer.domain import AccountState, InstrumentMetadata, MarketData, OrderIntent, OrderSide, OrderType
from preflight_layer.order_manager import OrderManager
from preflight_layer.validator import PreFlightValidator


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
    import time
    return MarketData(
        bid=Decimal("60000"),
        ask=Decimal("60000"),
        last=Decimal("60000"),
        timestamp=time.time(),
    )


def rejected_intent():
    return OrderIntent(
        instrument_id="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("60000.05"),
        size=Decimal("0.01"),
        leverage=Decimal("3"),
        margin_mode="cross",
        position_side="net",
        reduce_only=False,
        client_order_id="pf031",
    )



async def test_account_adapter_preserves_real_available_margin():
    from adapters.okx_adapter import OKXPreFlightAdapter

    exchange = Mock()
    exchange.exchange = Mock()
    exchange.exchange.fetch_balance = AsyncMock(
        return_value={
            "USDT": {"total": 1250.0, "free": 137.5}
        }
    )
    adapter = OKXPreFlightAdapter(exchange)

    snapshot = await adapter.fetch_account_state()

    assert snapshot.balance == Decimal("1250.0")
    assert snapshot.available_margin == Decimal("137.5")
    assert snapshot.available_margin != snapshot.balance
