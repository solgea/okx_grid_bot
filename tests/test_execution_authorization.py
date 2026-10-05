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



@pytest.mark.asyncio
async def test_demo_security_rejects_non_demo_read_only_bootstrap_before_exchange(monkeypatch):
    from config.settings import config
    from engine.exchange import OKXEngine

    monkeypatch.setattr(config, "IS_DEMO", False)
    engine = OKXEngine.__new__(OKXEngine)

    class ForbiddenExchange:
        async def load_markets(self):
            raise AssertionError("exchange must not be touched")

    engine.exchange = ForbiddenExchange()

    with pytest.raises(RuntimeError, match="IS_DEMO=true"):
        await engine.read_only_bootstrap()


@pytest.mark.asyncio
async def test_demo_security_unknown_batch_fails_closed_without_retry():
    from engine.sync_engine import ExecutionStatus, OrderSyncEngine

    intent = make_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])

    class UnknownExchange:
        def __init__(self):
            self.create_calls = 0

        async def fetch_open_orders(self, symbol):
            return []

        async def create_orders(self, symbol, orders):
            self.create_calls += 1
            return [{"status": "open"} for _ in orders]

    exchange = UnknownExchange()
    sync = OrderSyncEngine(exchange)

    with pytest.raises(RuntimeError, match="UNKNOWN"):
        await sync.sync_orders([intent], authorization=authorization)

    assert exchange.create_calls == 1
    assert ExecutionStatus.UNKNOWN.value == "UNKNOWN"


@pytest.mark.asyncio
async def test_demo_security_explicit_rejection_is_not_unknown():
    from engine.sync_engine import ExecutionStatus, OrderSyncEngine

    intent = make_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])

    class RejectedExchange:
        async def fetch_open_orders(self, symbol):
            return []

        async def create_orders(self, symbol, orders):
            return [{"info": {"sCode": "51008"}, "status": "rejected"} for _ in orders]

    sync = OrderSyncEngine(RejectedExchange())

    # Explicit exchange rejection is classified as REJECTED, not UNKNOWN.
    report = await sync._place_batch([
        sync._build_target_orders([intent], is_limit_breached=False)[0]
    ])
    assert report.statuses == (ExecutionStatus.REJECTED,)


def test_demo_security_live_path_stays_double_gated(monkeypatch):
    from config.settings import config
    from engine.exchange import OKXEngine

    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(config, "LIVE_TRADING_AUTHORIZED", False)

    engine = OKXEngine.__new__(OKXEngine)

    with pytest.raises(PermissionError, match="explicit live authorization"):
        engine._assert_mutation_authorized()


def test_demo_security_defaults_keep_live_and_emergency_paths_closed():
    from config.settings import config

    assert config.IS_DEMO is True
    assert config.DRY_RUN is True
    assert config.LIVE_TRADING_ENABLED is False
    assert config.LIVE_TRADING_AUTHORIZED is False
    assert config.EMERGENCY_FLATTEN_ENABLED is False
    assert config.EMERGENCY_FLATTEN_AUTHORIZED is False


def test_demo_security_read_only_bootstrap_forbids_mutations_by_contract():
    from scripts.okx_read_only_bootstrap import FORBIDDEN_MUTATIONS

    forbidden = set(FORBIDDEN_MUTATIONS)
    assert {
        "create_order",
        "create_orders",
        "cancel_order",
        "cancel_orders",
        "cancel_all_orders",
        "edit_order",
        "set_leverage",
        "set_margin_mode",
        "set_position_mode",
    }.issubset(forbidden)
