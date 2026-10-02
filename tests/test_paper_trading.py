import json
import time
import threading
import urllib.error
import urllib.request

import pytest

from paper_trading import PaperTradingError, PaperTradingManager
from app import create_server


def test_paper_trade_opens_and_closes_long_with_pnl_and_fees(tmp_path):
    manager = PaperTradingManager(tmp_path / "state.json")
    now = time.time()
    manager.on_price(2000, timestamp=now)
    agent = manager.create_agent("Test ajan")

    opened = manager.place_order(agent["id"], "buy", 10)
    manager.on_price(2100, timestamp=now + 1)
    state = manager.get_state()

    assert opened["notional"] == 200.0
    assert state["positions"][0]["side"] == "long"
    assert state["unrealized_pnl"] == pytest.approx(10.0)

    closed = manager.place_order(agent["id"], "sell", 10)
    state = manager.get_state()
    assert closed["realized_pnl"] == pytest.approx(9.895)
    assert state["positions"] == []
    assert state["realized_pnl"] == pytest.approx(9.8)


def test_agent_trade_stays_paper_and_state_survives_restart(tmp_path):
    state_path = tmp_path / "paper.json"
    manager = PaperTradingManager(state_path)
    manager.on_price(2000)
    agent = manager.create_agent("Trend bot", contracts=2, leverage=3)
    manager.place_order(agent["id"], "buy", 2)

    restored = PaperTradingManager(state_path)
    state = restored.get_state()
    assert state["mode"] == "paper"
    assert state["positions"][0]["contracts"] == 2
    assert state["agents"][0]["leverage"] == 3
    assert len(state["fills"]) == 1


def test_agent_ema_crossover_generates_only_simulated_order(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    agent = manager.create_agent("Trend bot")
    now = time.time()
    manager.on_price(100, timestamp=now)
    manager.set_agent_active(agent["id"], True)

    for index in range(1, 40):
        manager.on_price(100 - index, timestamp=now + index)
    for index in range(40, 90):
        manager.on_price(60 + index, timestamp=now + index)

    state = manager.get_state()
    assert state["fills"]
    assert all(fill["source"] == "EMA 9/21" for fill in state["fills"])
    assert state["mode"] == "paper"


def test_stale_market_and_invalid_order_are_rejected(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    agent = manager.create_agent("Test ajan")

    with pytest.raises(PaperTradingError, match="güncel"):
        manager.place_order(agent["id"], "buy", 1)
    with pytest.raises(PaperTradingError, match="tam sayı"):
        manager.create_agent("Hatalı ajan", contracts=True)
    with pytest.raises(PaperTradingError, match="1-5x"):
        manager.create_agent("Hatalı kaldıraç", leverage=10)
    with pytest.raises(PaperTradingError, match="metin"):
        manager.create_agent(123)


def test_insufficient_margin_rejects_order_without_mutating_state(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    manager._balance = 1
    manager._initial_balance = 1
    manager.on_price(2000)
    agent = manager.create_agent("Test ajan", contracts=100, leverage=1)

    with pytest.raises(PaperTradingError, match="teminat"):
        manager.place_order(agent["id"], "buy", 100)
    assert manager.get_state()["positions"] == []


def test_drawdown_limit_closes_position_and_stops_agent(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    manager.on_price(2000)
    agent = manager.create_agent("Risk ajanı", contracts=100, leverage=5)
    manager.set_agent_active(agent["id"], True)
    manager.place_order(agent["id"], "buy", 100)

    manager.on_price(1000)

    state = manager.get_state()
    assert state["positions"] == []
    assert state["agents"][0]["active"] is False
    assert "zarar limiti" in state["agents"][0]["halt_reason"]
    assert state["fills"][0]["source"] == "Zarar durdurma"


def test_local_dashboard_api_reports_paper_mode_and_creates_agent(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    server = create_server(0, manager)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(f"{base_url}/api/state") as response:
            state = json.load(response)
        assert state["mode"] == "paper"

        request = urllib.request.Request(
            f"{base_url}/api/agents",
            data=json.dumps({"name": "HTTP ajan"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            created = json.load(response)
        assert created["agent"]["name"] == "HTTP ajan"

        request = urllib.request.Request(
            f"{base_url}/api/agents/not-found/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
