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


def invalid_intent():
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
async def test_rejected_batch_is_not_forwarded():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", False)
    try:
        adapter = Mock()
        adapter.fetch_open_orders = AsyncMock(return_value=[])
        adapter.create_orders = AsyncMock(return_value=[])

        validator = PreFlightValidator()
        manager = OrderManager(adapter=adapter, validator=validator)
        accepted = manager.validate_intents([invalid_intent()], metadata(), account(), market())

        assert accepted == []
        assert validator.state.name == "REJECTED"

        sync = OrderSyncEngine(adapter)
        await sync.sync_orders(accepted)

        adapter.fetch_open_orders.assert_awaited_once()
        adapter.create_orders.assert_not_awaited()
    finally:
        monkeypatch.undo()
