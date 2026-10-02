import json
import threading
import urllib.error
import urllib.request

import pytest

from app import create_server
from config.settings import CCXT_SYMBOL, config
from demo_trading import DemoTradingError, DemoTradingManager


class FakeOKXDemo:
    def __init__(self, credentials):
        self.credentials = credentials
        self.has = {"fetchPositions": True}
        self.sandbox = False
        self.calls = []
        self.markets = {}
        self.order = None

    def set_sandbox_mode(self, enabled):
        self.sandbox = enabled
        self.calls.append(("sandbox", enabled))

    def load_markets(self):
        self.calls.append(("load_markets",))
        self.markets[CCXT_SYMBOL] = {
            "limits": {"amount": {"min": 0.01}},
        }
        return self.markets

    def fetch_balance(self):
        return {"USDT": {"free": "100", "total": "125"}}

    def fetch_positions(self, symbols):
        assert symbols == [CCXT_SYMBOL]
        return [
            {
                "symbol": CCXT_SYMBOL,
                "side": "long",
                "contracts": "0.01",
                "entryPrice": "3500",
                "markPrice": "3510",
                "unrealizedPnl": "0.1",
                "leverage": "2",
            }
        ]

    def fetch_open_orders(self, symbol):
        assert symbol == CCXT_SYMBOL
        return []

    def market(self, symbol):
        return self.markets[symbol]

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.2f}"

    def price_to_precision(self, symbol, price):
        return f"{price:.1f}"

    def create_order(self, *args):
        self.order = args
        return {
            "id": "demo-order-1",
            "symbol": CCXT_SYMBOL,
            "type": args[1],
            "side": args[2],
            "amount": args[3],
            "price": args[4],
            "status": "open",
        }

    def close(self):
        self.calls.append(("close",))


@pytest.fixture
def demo_exchange(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "demo-key")
    monkeypatch.setattr(config, "API_SECRET", "demo-secret")
    monkeypatch.setattr(config, "PASSPHRASE", "demo-passphrase")
    monkeypatch.setattr(config, "IS_DEMO", True)
    instances = []

    def factory(credentials):
        exchange = FakeOKXDemo(credentials)
        instances.append(exchange)
        return exchange

    manager = DemoTradingManager(factory)
    return manager, instances


def test_demo_state_forces_sandbox_and_hides_credentials(demo_exchange):
    manager, instances = demo_exchange

    state = manager.get_state()

    assert state["connected"] is True
    assert state["mode"] == "demo"
    assert state["balance"] == 100
    assert state["positions"][0]["side"] == "long"
    assert "demo-key" not in json.dumps(state)
    assert instances[0].sandbox is True
    assert instances[0].calls[:2] == [("sandbox", True), ("load_markets",)]
    manager.close()
    assert manager._exchange is None


@pytest.mark.parametrize(
    ("side", "order_type", "price"),
    [("buy", "limit", 3500.25), ("sell", "market", None)],
)
def test_confirmed_demo_order_uses_sandbox_and_one_contract_cap(
    demo_exchange, side, order_type, price
):
    manager, instances = demo_exchange

    order = manager.place_order(side, order_type, 1, price, confirm=True)

    assert order["mode"] == "demo"
    assert order["id"] == "demo-order-1"
    assert order["side"] == side
    assert instances[0].sandbox is True
    assert instances[0].order[:5] == (
        CCXT_SYMBOL,
        order_type,
        side,
        1.0,
        3500.2 if order_type == "limit" else None,
    )
    assert instances[0].order[5] == {"tdMode": "cross"}


def test_demo_order_requires_confirmation_and_rejects_out_of_range_order(
    demo_exchange,
):
    manager, instances = demo_exchange

    with pytest.raises(DemoTradingError, match="onay"):
        manager.place_order("buy", "market", 0.01, None, confirm=False)
    with pytest.raises(DemoTradingError, match="en fazla"):
        manager.place_order("buy", "market", 1.01, None, confirm=True)
    with pytest.raises(DemoTradingError, match="Limit emri"):
        manager.place_order("buy", "limit", 0.01, None, confirm=True)
    assert instances == []


def test_demo_orders_are_blocked_when_live_mode_is_configured(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "configured")
    monkeypatch.setattr(config, "API_SECRET", "configured")
    monkeypatch.setattr(config, "PASSPHRASE", "configured")
    monkeypatch.setattr(config, "IS_DEMO", False)
    created = []
    manager = DemoTradingManager(lambda credentials: created.append(credentials))

    with pytest.raises(DemoTradingError, match="canlı"):
        manager.place_order("buy", "market", 0.01, None, confirm=True)
    assert manager.get_state()["connected"] is False
    assert created == []


def test_demo_order_confirmation_is_required_by_http_api(demo_exchange):
    manager, instances = demo_exchange
    server = create_server(0, demo_manager=manager)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        request = urllib.request.Request(
            f"{base_url}/api/demo/orders",
            data=json.dumps(
                {
                    "side": "buy",
                    "type": "market",
                    "contracts": 0.01,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 400
        assert instances == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_demo_order_rejects_cross_origin_and_non_json_requests(demo_exchange):
    manager, instances = demo_exchange
    server = create_server(0, demo_manager=manager)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        payload = json.dumps(
            {
                "side": "buy",
                "type": "market",
                "contracts": 0.01,
                "confirm": True,
            }
        ).encode()
        cross_origin = urllib.request.Request(
            f"{base_url}/api/demo/orders",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Origin": "http://attacker.example",
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as origin_error:
            urllib.request.urlopen(cross_origin)
        assert origin_error.value.code == 403

        form_request = urllib.request.Request(
            f"{base_url}/api/demo/orders",
            data=payload,
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as content_error:
            urllib.request.urlopen(form_request)
        assert content_error.value.code == 415
        assert instances == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
