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


# --- agent update / delete / enable-disable -----------------------------------
def test_update_agent_changes_name_size_and_leverage_and_persists(tmp_path):
    state_path = tmp_path / "paper.json"
    manager = PaperTradingManager(state_path)
    agent = manager.create_agent("Eski ad", contracts=1, leverage=2)

    updated = manager.update_agent(agent["id"], name="  Yeni ad  ", contracts=5, leverage=3)

    assert updated["name"] == "Yeni ad" and updated["contracts"] == 5 and updated["leverage"] == 3
    restored = PaperTradingManager(state_path).get_state()["agents"][0]
    assert (restored["name"], restored["contracts"], restored["leverage"]) == ("Yeni ad", 5, 3)


def test_update_agent_validates_input_and_requires_a_field(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    agent = manager.create_agent("Ajan")
    with pytest.raises(PaperTradingError, match="belirtilmedi"):
        manager.update_agent(agent["id"])
    with pytest.raises(PaperTradingError, match="1-40"):
        manager.update_agent(agent["id"], name="   ")
    with pytest.raises(PaperTradingError, match="1-40"):
        manager.update_agent(agent["id"], name="x" * 41)
    with pytest.raises(PaperTradingError, match="metin"):
        manager.update_agent(agent["id"], name=5)
    with pytest.raises(PaperTradingError, match="tam sayı"):
        manager.update_agent(agent["id"], contracts=True)
    with pytest.raises(PaperTradingError, match="1-5x"):
        manager.update_agent(agent["id"], leverage=6)
    with pytest.raises(PaperTradingError, match="bulunamadı"):
        manager.update_agent("missing", name="x")
    # nothing above may have changed the agent
    assert manager.get_state()["agents"][0]["name"] == "Ajan"
    assert manager.get_state()["agents"][0]["contracts"] == 1


def test_update_agent_blocks_risk_changes_while_position_is_open(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    manager.on_price(2000)
    agent = manager.create_agent("Ajan", contracts=2, leverage=2)
    manager.place_order(agent["id"], "buy", 2)

    with pytest.raises(PaperTradingError, match="pozisyon"):
        manager.update_agent(agent["id"], contracts=10)
    with pytest.raises(PaperTradingError, match="pozisyon"):
        manager.update_agent(agent["id"], leverage=5)
    renamed = manager.update_agent(agent["id"], name="Yeniden adlandı")      # name is always safe
    same = manager.update_agent(agent["id"], contracts=2, leverage=2)        # unchanged values are fine
    assert renamed["name"] == "Yeniden adlandı" and same["contracts"] == 2

    manager.close_position(agent["id"])
    assert manager.update_agent(agent["id"], contracts=10)["contracts"] == 10


def test_delete_agent_removes_it_and_keeps_account_balance(tmp_path):
    state_path = tmp_path / "paper.json"
    manager = PaperTradingManager(state_path)
    manager.on_price(2000)
    keep = manager.create_agent("Kalacak")
    gone = manager.create_agent("Silinecek", contracts=10)
    manager.place_order(gone["id"], "buy", 10)
    manager.on_price(2100)
    manager.close_position(gone["id"])
    balance = manager.get_state()["balance"]

    deleted = manager.delete_agent(gone["id"])

    state = manager.get_state()
    assert deleted["id"] == gone["id"]
    assert [a["id"] for a in state["agents"]] == [keep["id"]]
    assert state["balance"] == balance                       # realized PnL stays in the account
    assert state["fills"]                                    # trade history is kept
    assert [a["id"] for a in PaperTradingManager(state_path).get_state()["agents"]] == [keep["id"]]
    with pytest.raises(PaperTradingError, match="bulunamadı"):
        manager.set_agent_active(gone["id"], True)
    with pytest.raises(PaperTradingError, match="bulunamadı"):
        manager.delete_agent(gone["id"])


def test_delete_agent_refused_while_position_is_open(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    manager.on_price(2000)
    agent = manager.create_agent("Ajan")
    manager.place_order(agent["id"], "buy", 1)

    with pytest.raises(PaperTradingError, match="pozisyon"):
        manager.delete_agent(agent["id"])
    assert len(manager.get_state()["agents"]) == 1 and manager.get_state()["positions"]


def test_deleting_an_active_flat_agent_stops_trading_for_it(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    now = time.time()
    manager.on_price(100, timestamp=now)
    agent = manager.create_agent("Trend")
    manager.set_agent_active(agent["id"], True)
    manager.delete_agent(agent["id"])
    for index in range(1, 80):                                   # would trigger EMA crossovers
        manager.on_price(100 + (index % 2) * 30 + (-1) ** index * index, timestamp=now + index)
    assert manager.get_state()["fills"] == [] and manager.get_state()["agents"] == []


def test_enable_disable_cycle_and_agent_cap_frees_up_after_delete(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    manager.on_price(2000)
    agents = [manager.create_agent(f"A{i}") for i in range(10)]
    with pytest.raises(PaperTradingError, match="10"):
        manager.create_agent("Fazla")
    assert manager.set_agent_active(agents[0]["id"], True)["active"] is True
    assert manager.set_agent_active(agents[0]["id"], False)["active"] is False
    manager.delete_agent(agents[0]["id"])
    assert manager.create_agent("Yeni")["name"] == "Yeni"


def _post(base_url, path, payload):
    request = urllib.request.Request(
        f"{base_url}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_dashboard_api_update_and_delete_agent(tmp_path):
    manager = PaperTradingManager(tmp_path / "paper.json")
    server = create_server(0, manager)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        _, created = _post(base, "/api/agents", {"name": "HTTP", "contracts": 1, "leverage": 2})
        agent_id = created["agent"]["id"]

        status, body = _post(base, f"/api/agents/{agent_id}/update", {"name": "Yeni", "contracts": 3})
        assert status == 200 and body["agent"]["name"] == "Yeni" and body["agent"]["contracts"] == 3

        status, body = _post(base, f"/api/agents/{agent_id}/update", {"leverage": 99})
        assert status == 400 and "1-5x" in body["error"]
        status, _ = _post(base, f"/api/agents/{agent_id}/update", {})
        assert status == 400

        status, body = _post(base, f"/api/agents/{agent_id}/delete", {})        # no confirm -> refused
        assert status == 400 and "onay" in body["error"]
        status, body = _post(base, f"/api/agents/{agent_id}/delete", {"confirm": "true"})  # truthy string is not enough
        assert status == 400
        assert len(manager.get_state()["agents"]) == 1

        status, body = _post(base, f"/api/agents/{agent_id}/delete", {"confirm": True})
        assert status == 200 and body["agent"]["id"] == agent_id
        assert manager.get_state()["agents"] == []

        status, _ = _post(base, f"/api/agents/{agent_id}/delete", {"confirm": True})
        assert status == 400                                                    # already gone
        status, _ = _post(base, f"/api/agents/{agent_id}/bogus", {})
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
