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


@pytest.mark.asyncio
async def test_pf031_rejected_batch_never_reaches_submission(monkeypatch):
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", False)

    exchange = Mock()
    exchange.fetch_open_orders = AsyncMock(return_value=[])
    exchange.create_orders = AsyncMock(return_value=[])

    validator = PreFlightValidator()
    manager = OrderManager(adapter=exchange, validator=validator)

    accepted = manager.validate_intents([rejected_intent()], metadata(), account(), market())

    assert accepted == []
    assert validator.state.value == "REJECTED"

    sync = OrderSyncEngine(exchange)
    await sync.sync_orders(accepted)

    exchange.fetch_open_orders.assert_awaited_once()
    exchange.create_orders.assert_not_awaited()
