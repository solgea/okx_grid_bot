"""Regression: the trading loop must pass the instrument metadata to PreFlight.

The instrument metadata is fetched once at startup. If it is not handed to
the order manager, every intent is rejected with
PF026_MARKET_DATA_UNAVAILABLE and the bot never places an order.
"""
import asyncio
from decimal import Decimal

import pytest

from bot.kill_switch import KillSwitch
from bot.market_state import MarketState
from bot.trade_log import TradeLog
from bot.trading_loop import TradingLoop
from preflight_layer.domain import InstrumentMetadata


class RecordingOrderManager:
    """Captures the arguments the trading loop authorizes."""

    def __init__(self):
        self.calls = []

    def authorize_intents(self, intents, metadata, account, market):
        self.calls.append((intents, metadata, account, market))
        return list(intents), "authorization-token"


def build_loop(order_manager, metadata):
    class FakeEngine:
        connected = True

        async def fetch_position(self, symbol):
            return {"size": 0.0, "entryPrice": 0.0, "unrealizedPnl": 0.0}

        async def fetch_open_orders(self, symbol):
            return []

    class FakeAdapter:
        async def fetch_account_state(self):
            class Account:
                balance = Decimal("1000")
                available_margin = Decimal("1000")
                leverage = Decimal("10")
                current_position_size = Decimal("0")
                open_order_exposure = Decimal("0")

            return Account()

    class FakeSync:
        def __init__(self):
            self.calls = []

        async def sync_orders(self, intents, authorization, is_limit_breached):
            self.calls.append((intents, authorization, is_limit_breached))

    class FakeRisk:
        state_dirty = False
        kill_switch_triggered = False
        trading_halted = False

        def check_risk_limits(self, balance, size):
            return False

        def export_state(self):
            return {}

        def mark_state_persisted(self):
            pass

    class FakeGrid:
        def get_target_orders(self, **kwargs):
            return ["intent"]

        def update_grid_from_smc(self, smc_data, price):
            pass

    return TradingLoop(
        engine=FakeEngine(),
        exchange_adapter=FakeAdapter(),
        order_manager=order_manager,
        sync=FakeSync(),
        risk=FakeRisk(),
        grid=FakeGrid(),
        state=MarketState(),
        trade_log=TradeLog("unused.csv"),
        kill_switch=KillSwitch(FakeEngine(), "ETH/USDT:USDT"),
        stop_event=asyncio.Event(),
        initial_balance=1000.0,
        instrument_metadata=metadata,
    )


@pytest.mark.asyncio
async def test_instrument_metadata_reaches_preflight():
    """The metadata fetched at startup must be the one PreFlight validates."""
    metadata = InstrumentMetadata(
        symbol="ETH/USDT:USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("0.01"),
        contract_type="linear",
        is_live=True,
    )
    order_manager = RecordingOrderManager()
    loop = build_loop(order_manager, metadata)
    await loop.state.update_price(2500.0)

    await loop._cycle()

    assert order_manager.calls, "the trading loop did not authorize any intents"
    authorized_intents, authorized_metadata, account, market = order_manager.calls[0]
    assert authorized_metadata is metadata
    assert authorized_intents == ["intent"]
    assert market.last == Decimal("2500")
