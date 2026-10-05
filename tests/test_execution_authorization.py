from decimal import Decimal
from types import SimpleNamespace

import pytest

from engine.sync_engine import OrderSyncEngine
from preflight_layer.domain import (
    ExecutionAuthorization,
    OrderIntent,
    OrderSide,
    OrderType,
    PreFlightState,
)
from preflight_layer.order_manager import OrderManager


def make_intent(client_order_id="intent-1", price="2500"):
    return OrderIntent(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal(price),
        size=Decimal("0.01"),
        leverage=Decimal("2"),
        margin_mode="cross",
        position_side="net",
        client_order_id=client_order_id,
    )


class FakeValidator:
    def __init__(self, accepted, rejected=()):
        self.accepted = list(accepted)
        self.rejected = list(rejected)

    def validate_batch(self, intents, metadata, account, market):
        return list(self.accepted), list(self.rejected)


class ExchangeBoundaryProbe:
    def __init__(self):
        self.fetch_open_orders_called = False
        self.create_orders_called = False

    async def fetch_open_orders(self, symbol):
        self.fetch_open_orders_called = True
        return []

    async def create_orders(self, symbol, orders):
        self.create_orders_called = True
        return [{"id": "simulated-authorized-order", "status": "open"} for _ in orders]


@pytest.mark.asyncio
async def test_rejected_preflight_cannot_reach_execution_boundary():
    intent = make_intent()
    rejection = SimpleNamespace(
        rejection_code="PF030_TRADING_HALTED",
        message="Trading is halted.",
    )
    manager = OrderManager(
        adapter=object(),
        validator=FakeValidator([], [(intent, rejection)]),
    )

    accepted, authorization = manager.authorize_intents(
        [intent], metadata=object(), account=object(), market=object()
    )

    assert accepted == []
    assert authorization.authorized is False
    assert authorization.state is PreFlightState.REJECTED

    probe = ExchangeBoundaryProbe()
    sync = OrderSyncEngine(probe)

    with pytest.raises(PermissionError):
        await sync.sync_orders(
            [intent],
            authorization=authorization,
        )

    assert probe.fetch_open_orders_called is False


@pytest.mark.asyncio
async def test_authorized_intents_must_match_execution_payload():
    intent = make_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])
    probe = ExchangeBoundaryProbe()
    sync = OrderSyncEngine(probe)

    mutated = make_intent(price="2501")

    with pytest.raises(PermissionError, match="does not match"):
        await sync.sync_orders(
            [mutated],
            authorization=authorization,
        )

    assert probe.fetch_open_orders_called is False


@pytest.mark.asyncio
async def test_authorized_intents_can_reach_reconciliation():
    intent = make_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])
    probe = ExchangeBoundaryProbe()
    sync = OrderSyncEngine(probe)

    await sync.sync_orders(
        [intent],
        authorization=authorization,
    )

    assert probe.fetch_open_orders_called is True
    assert probe.create_orders_called is True
