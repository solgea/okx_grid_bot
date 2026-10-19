"""Phase 0 safety regressions.

Covers the four Phase 0 fixes:
1. PreFlight rejects an unsupported contract type with PF014 (no NameError).
2. The order-amend path runs through the OKXEngine authorization gate.
3. The authorization fingerprint binds the risk-relevant execution context.
4. The Demo panel and paper book follow the configured SYMBOL.
"""
import time
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from config.settings import config, to_native_symbol
from demo_trading import DemoTradingManager
from engine.exchange import OKXEngine
from engine.sync_engine import OrderSyncEngine
from paper_trading import PaperTradingManager
from preflight_layer.domain import (
    AccountState,
    ExecutionAuthorization,
    InstrumentMetadata,
    MarketData,
    OrderIntent,
    OrderSide,
    OrderType,
)
from preflight_layer.validator import PreFlightValidator


# --- 1. unsupported contract type -------------------------------------------
def test_unsupported_contract_type_is_rejected_with_pf014(monkeypatch):
    """A bad contract type must fail closed with a rejection code, not crash."""
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", False)
    metadata = InstrumentMetadata(
        symbol="ETH/USDT:USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("0.01"),
        contract_type="unsupported",
    )
    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("10"),
    )
    market = MarketData(
        bid=Decimal("2500"),
        ask=Decimal("2500"),
        last=Decimal("2500"),
        timestamp=time.time(),
    )
    intent = OrderIntent(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("2500"),
        size=Decimal("0.01"),
    )

    result = PreFlightValidator().validate(intent, metadata, account, market)

    assert result.passed is False
    assert result.rejection_code == "PF014_INVALID_CONTRACT_TYPE"


# --- 2. amend path is authorization gated ------------------------------------
@pytest.mark.asyncio
async def test_amend_path_is_blocked_without_live_authorization(monkeypatch):
    """The amend path must not reach the exchange when live trading is closed."""
    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(config, "LIVE_TRADING_AUTHORIZED", False)

    engine = OKXEngine.__new__(OKXEngine)
    engine.connected = True
    exchange = Mock()
    exchange.edit_order = AsyncMock()
    engine.exchange = exchange

    with pytest.raises(PermissionError, match="explicit live authorization"):
        await engine.edit_order(
            order_id="ord-1", symbol="ETH/USDT:USDT", amount=0.01, price=2500.0
        )

    exchange.edit_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_amend_path_is_simulated_in_dry_run(monkeypatch):
    """DRY_RUN must simulate the amend instead of mutating exchange state."""
    monkeypatch.setattr(config, "IS_DEMO", True)
    monkeypatch.setattr(config, "DRY_RUN", True)

    engine = OKXEngine.__new__(OKXEngine)
    engine.connected = True
    exchange = Mock()
    exchange.edit_order = AsyncMock()
    engine.exchange = exchange

    result = await engine.edit_order(
        order_id="ord-1", symbol="ETH/USDT:USDT", amount=0.01, price=2500.0
    )

    assert result["status"] == "simulated"
    assert result["id"] == "ord-1"
    exchange.edit_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_engine_amend_routes_through_the_engine_gate(monkeypatch):
    """OrderSyncEngine must not call the raw ccxt client for amendments."""
    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", False)
    monkeypatch.setattr(config, "LIVE_TRADING_AUTHORIZED", False)

    exchange = Mock()
    exchange.edit_order = AsyncMock()
    engine = Mock()
    engine.exchange = exchange
    engine.edit_order = AsyncMock(side_effect=PermissionError("live gate closed"))

    sync = OrderSyncEngine(engine)
    spec = Mock()
    spec.ord_id = "ord-1"
    spec.new_size = Decimal("0.01")
    spec.new_price = Decimal("2500")

    with pytest.raises(PermissionError, match="live gate closed"):
        await sync._amend_single_order(spec)

    engine.edit_order.assert_awaited_once()
    exchange.edit_order.assert_not_awaited()


# --- 3. fingerprint binds risk-relevant context ------------------------------
def _authorized_intent(**overrides):
    intent = OrderIntent(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("2500"),
        size=Decimal("0.01"),
        expected_target_price=Decimal("2600"),
        is_maker=True,
    )
    for name, value in overrides.items():
        setattr(intent, name, value)
    return intent


@pytest.mark.asyncio
async def test_authorization_rejects_changed_target_price():
    """An authorization token must not validate a different expected target."""
    intent = _authorized_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])

    mutated = _authorized_intent(expected_target_price=Decimal("9999"))

    engine = Mock()
    engine.fetch_open_orders = AsyncMock(return_value=[])
    sync = OrderSyncEngine(engine)

    with pytest.raises(PermissionError, match="does not match"):
        await sync.sync_orders([mutated], authorization=authorization)

    engine.fetch_open_orders.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorization_rejects_changed_maker_flag():
    """An authorization token must not validate a different maker/taker mode."""
    intent = _authorized_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])

    mutated = _authorized_intent(is_maker=False)

    engine = Mock()
    engine.fetch_open_orders = AsyncMock(return_value=[])
    sync = OrderSyncEngine(engine)

    with pytest.raises(PermissionError, match="does not match"):
        await sync.sync_orders([mutated], authorization=authorization)

    engine.fetch_open_orders.assert_not_awaited()


@pytest.mark.asyncio
async def test_unchanged_execution_context_still_authorizes():
    """The fingerprint change must not break the legitimate execution path."""
    intent = _authorized_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])

    engine = Mock()
    engine.fetch_open_orders = AsyncMock(return_value=[])
    engine.create_orders = AsyncMock(return_value=[{"id": "1", "status": "open"}])
    sync = OrderSyncEngine(engine)

    await sync.sync_orders([intent], authorization=authorization)

    engine.create_orders.assert_awaited_once()


# --- 4. symbol configuration --------------------------------------------------
def test_native_symbol_derivation():
    assert to_native_symbol("ETH/USDT:USDT") == "ETH-USDT-SWAP"
    assert to_native_symbol("BTC/USDT:USDT") == "BTC-USDT-SWAP"


@pytest.mark.parametrize("bad_symbol", ["ETHUSDT", "", "ETH/"])
def test_native_symbol_rejects_malformed_symbols(bad_symbol):
    with pytest.raises(ValueError):
        to_native_symbol(bad_symbol)


def test_demo_panel_follows_the_configured_symbol(monkeypatch):
    """The Demo panel must trade config.SYMBOL, not a hardcoded instrument."""
    monkeypatch.setattr(config, "SYMBOL", "BTC/USDT:USDT")

    manager = DemoTradingManager(lambda credentials: None)

    assert manager.symbol == "BTC/USDT:USDT"
    assert manager.native_symbol == "BTC-USDT-SWAP"
    assert manager._state_error("unavailable")["symbol"] == "BTC/USDT:USDT"
    assert manager._state_error("unavailable")["instrument"] == "BTC-USDT-SWAP"


def test_paper_book_follows_the_configured_symbol(monkeypatch):
    """The paper book must report the configured instrument."""
    monkeypatch.setattr(config, "SYMBOL", "BTC/USDT:USDT")

    manager = PaperTradingManager("unused-state.json")

    assert manager.get_state()["instrument"] == "BTC-USDT-SWAP"
