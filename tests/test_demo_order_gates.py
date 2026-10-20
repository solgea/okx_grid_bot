"""Regression tests for the dashboard Demo order path.

The panel places a real order on the OKX Demo sandbox, so it must obey the
same gates as the bot: DRY_RUN must not be bypassed, and PreFlight must
authorize the order before anything reaches the exchange.
"""
import json
import threading
import time
import urllib.request

import pytest

from config.settings import CCXT_SYMBOL, config
from demo_trading import DemoTradingError, DemoTradingManager


class RecordingExchange:
    """Fake OKX Demo exchange that records every call."""

    def __init__(self):
        self.has = {"fetchPositions": True}
        self.sandbox = False
        self.calls = []
        self.orders = []
        self.markets = {}

    def set_sandbox_mode(self, enabled):
        self.sandbox = enabled
        self.calls.append(("sandbox", enabled))

    def load_markets(self):
        self.calls.append(("load_markets",))
        self.markets[CCXT_SYMBOL] = {
            "limits": {"amount": {"min": 0.01}},
            "precision": {"price": 0.1, "amount": 0.01},
            "info": {
                "minSz": "0.01",
                "lotSz": "0.01",
                "tickSz": "0.1",
                "ctVal": "0.01",
                "ctType": "linear",
                "state": "live",
            },
        }
        return self.markets

    def fetch_balance(self):
        return {"USDT": {"free": "100", "total": "125"}}

    def fetch_ticker(self, symbol):
        assert symbol == CCXT_SYMBOL
        return {
            "last": 3500.0,
            "bid": 3499.9,
            "ask": 3500.1,
            "timestamp": int(time.time() * 1000),
        }

    def fetch_positions(self, symbols):
        return []

    def fetch_open_orders(self, symbol):
        return []

    def market(self, symbol):
        return self.markets[symbol]

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.2f}"

    def price_to_precision(self, symbol, price):
        return f"{price:.1f}"

    def create_order(self, *args):
        self.orders.append(args)
        return {"id": "demo-1", "status": "open"}

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def exchange(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "demo-key")
    monkeypatch.setattr(config, "API_SECRET", "demo-secret")
    monkeypatch.setattr(config, "PASSPHRASE", "demo-passphrase")
    monkeypatch.setattr(config, "IS_DEMO", True)
    monkeypatch.setattr(config, "DRY_RUN", False)
    instance = RecordingExchange()
    return instance


def test_dry_run_blocks_the_demo_order(exchange, monkeypatch):
    """DRY_RUN must not be bypassed by the dashboard."""
    monkeypatch.setattr(config, "DRY_RUN", True)
    manager = DemoTradingManager(lambda credentials: exchange)

    with pytest.raises(DemoTradingError, match="DRY_RUN"):
        manager.place_order(side="buy", order_type="limit", contracts=1, price=3500.25, confirm=True)

    assert exchange.orders == [], "an order was submitted while DRY_RUN was on"


def test_kill_switch_blocks_the_demo_order(exchange, monkeypatch):
    """The global kill switch must not be bypassed by the dashboard."""
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    manager = DemoTradingManager(lambda credentials: exchange)

    with pytest.raises(DemoTradingError, match="PF029"):
        manager.place_order(side="buy", order_type="limit", contracts=1, price=3500.25, confirm=True)

    assert exchange.orders == [], "an order was submitted while the kill switch was on"


def test_authorized_demo_order_reaches_the_exchange(exchange, monkeypatch):
    """A confirmed, authorized order is submitted to the Demo sandbox."""
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", False)
    manager = DemoTradingManager(lambda credentials: exchange)

    order = manager.place_order(
        side="buy", order_type="limit", contracts=1, price=3500.25, confirm=True
    )

    assert order["id"] == "demo-1"
    assert order["status"] == "open"
    assert len(exchange.orders) == 1
    assert exchange.orders[0][0] == CCXT_SYMBOL
    assert exchange.orders[0][2] == "buy"


def test_kill_switch_is_not_modified_by_a_demo_order(exchange, monkeypatch):
    """The panel must leave the global kill switch exactly as it found it."""
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    manager = DemoTradingManager(lambda credentials: exchange)

    with pytest.raises(DemoTradingError):
        manager.place_order(side="buy", order_type="limit", contracts=1, price=3500.25, confirm=True)

    assert config.KILL_SWITCH_ACTIVE is True


def test_kill_switch_is_not_modified_by_a_failed_demo_order(exchange, monkeypatch):
    """A failed order must not leave the kill switch disabled."""
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)

    def broken_factory(*args, **kwargs):
        raise RuntimeError("exchange unavailable")

    manager = DemoTradingManager(broken_factory)

    with pytest.raises(DemoTradingError):
        manager.place_order(side="buy", order_type="limit", contracts=1, price=3500.25, confirm=True)

    assert config.KILL_SWITCH_ACTIVE is True


def test_dashboard_api_refuses_the_order_in_dry_run(exchange, monkeypatch):
    """The HTTP surface must not bypass the DRY_RUN gate either."""
    from app import create_server

    monkeypatch.setattr(config, "DRY_RUN", True)
    manager = DemoTradingManager(lambda credentials: exchange)
    server = create_server(0, demo_manager=manager)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        request = urllib.request.Request(
            f"{base_url}/api/demo/orders",
            data=json.dumps(
                {"side": "buy", "type": "limit", "contracts": 0.01, "price": 3500, "confirm": True}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(Exception) as error:
            urllib.request.urlopen(request)
        assert getattr(error.value, "code", None) == 400
        assert exchange.orders == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_state_explains_why_orders_are_blocked(exchange, monkeypatch):
    """The panel state must say why an order cannot be placed."""
    manager = DemoTradingManager(lambda credentials: exchange)

    monkeypatch.setattr(config, "DRY_RUN", True)
    assert "DRY_RUN" in (manager.order_block_reason or "")

    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    assert "Kill switch" in (manager.order_block_reason or "")

    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", False)
    assert manager.order_block_reason is None


def test_state_carries_the_block_reason(exchange, monkeypatch):
    """The block reason must reach the panel state payload."""
    monkeypatch.setattr(config, "DRY_RUN", True)
    manager = DemoTradingManager(lambda credentials: exchange)

    state = manager.get_state()

    assert "DRY_RUN" in (state["order_block_reason"] or "")
