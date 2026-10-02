from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from config.settings import config
from engine.sync_engine import OrderSyncEngine
from strategy.order_reconciler import GridOrderSpec


@pytest.mark.asyncio
async def test_ten_new_orders_use_one_batch_request():
    engine = Mock()
    engine.create_orders = AsyncMock(return_value=[{"id": str(i)} for i in range(10)])
    sync = OrderSyncEngine(engine)
    specs = [
        GridOrderSpec(
            price=Decimal(str(100 + i)),
            size=Decimal("0.1"),
            side="buy",
            pos_side="net",
            cl_ord_id=f"grid-{i}",
        )
        for i in range(10)
    ]

    await sync._place_orders_async(specs)

    engine.create_orders.assert_awaited_once()
    symbol, payload = engine.create_orders.await_args.args
    assert len(payload) == 10
    assert symbol


@pytest.mark.asyncio
async def test_cancel_delta_uses_exchange_batch_method():
    engine = Mock()
    engine.cancel_orders = AsyncMock(return_value=[])
    sync = OrderSyncEngine(engine)

    await sync._cancel_orders_async(["1", "2", "3"])

    engine.cancel_orders.assert_awaited_once_with(["1", "2", "3"], config.SYMBOL)
