import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from ccxt.base.errors import NetworkError

from engine.exchange import OKXEngine
from engine.sync_engine import OrderSyncEngine


@pytest.mark.asyncio
async def test_open_order_disconnect_is_not_treated_as_empty_book():
    engine = OKXEngine.__new__(OKXEngine)
    engine.connected = True
    engine.exchange = Mock()
    engine.exchange.fetch_open_orders = AsyncMock(
        side_effect=NetworkError("socket disconnected")
    )

    with pytest.raises(NetworkError):
        await engine.fetch_open_orders("ETH/USDT:USDT")

    assert engine.connected is False


@pytest.mark.asyncio
async def test_sync_does_not_cancel_orders_when_snapshot_fails():
    exchange = Mock()
    exchange.cancel_orders = AsyncMock()
    engine = Mock()
    engine.fetch_open_orders = AsyncMock(side_effect=NetworkError("maintenance"))
    engine.exchange = exchange

    sync = OrderSyncEngine(engine)

    with pytest.raises(NetworkError):
        await sync.sync_orders([])

    exchange.cancel_orders.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconnect_is_serialized_and_restores_connection_state():
    engine = OKXEngine.__new__(OKXEngine)
    engine.connected = False
    engine.connection_generation = 0
    engine._connection_lock = asyncio.Lock()
    old_exchange = Mock()
    old_exchange.close = AsyncMock()
    engine.exchange = old_exchange

    new_exchange = Mock()
    new_exchange.set_sandbox_mode = Mock()
    new_exchange.close = AsyncMock()

    original_initialize = engine.initialize
    initialize_mock = AsyncMock(
        side_effect=lambda: setattr(engine, "connected", True)
        or setattr(engine, "connection_generation", engine.connection_generation + 1)
    )
    engine.initialize = initialize_mock

    import engine.exchange as exchange_module

    original_factory = exchange_module.ccxt.okx
    exchange_module.ccxt.okx = Mock(return_value=new_exchange)
    try:
        await asyncio.gather(engine.reconnect(), engine.reconnect())
    finally:
        exchange_module.ccxt.okx = original_factory
        engine.initialize = original_initialize

    assert old_exchange.close.await_count == 1
    assert initialize_mock.await_count == 1
    assert engine.connected is True
    assert engine.connection_generation == 1
