"""Phase 3 structural regressions.

Covers the extracted runtime components:
1. MarketState hands each SMC analysis to exactly one consumer, so the grid
   is updated once per analysis and no analysis is dropped.
2. BackoffPolicy reproduces the previous retry delays.
3. KillSwitch only flattens a position when explicitly authorized.
4. TradeLog classifies actions and writes the documented CSV shape.
5. The dashboard router preserves the HTTP contract of the old handler.
"""
import asyncio
import json
import threading
import urllib.error
import urllib.request

import pytest

from bot.backoff import BackoffPolicy
from bot.kill_switch import KillSwitch, emergency_flatten_authorized
from bot.market_state import MarketState
from bot.trade_log import TradeLog
from config.settings import config
from web.routes import dispatch_agent_action, is_agent_collection, parse_agent_action


# --- 1. market state ----------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_smc_is_handed_to_exactly_one_consumer():
    """An analysis must be applied once, not twice and not dropped."""
    state = MarketState()
    await state.publish_smc({"fvg": {"lower": 1}}, 80)

    first = await state.take_pending_smc()
    second = await state.take_pending_smc()

    assert first == {"fvg": {"lower": 1}}
    assert second is None


@pytest.mark.asyncio
async def test_market_state_tracks_price_and_confluence():
    state = MarketState()
    assert state.price is None
    assert state.confluence_score is None

    await state.update_price(2500.0)
    await state.publish_smc({"mss": "bullish"}, 75)

    assert state.price == 2500.0
    assert state.confluence_score == 75


@pytest.mark.asyncio
async def test_concurrent_consumers_never_share_one_analysis():
    """Exactly one consumer may receive a given analysis."""
    state = MarketState()
    await state.publish_smc({"mss": "bearish"}, 60)

    results = await asyncio.gather(
        state.take_pending_smc(),
        state.take_pending_smc(),
        state.take_pending_smc(),
    )

    assert sum(1 for result in results if result is not None) == 1


@pytest.mark.asyncio
async def test_restored_smc_is_available_to_the_loop():
    state = MarketState()
    await state.restore_smc({"mss": "bullish"})

    assert await state.take_pending_smc() == {"mss": "bullish"}


# --- 2. backoff --------------------------------------------------------------
def test_backoff_matches_the_previous_retry_delays():
    """The extracted policy must reproduce the original inline formula."""
    policy = BackoffPolicy()
    # Original formula: min(max_delay, base_delay * factor ** retry_count)
    assert policy.delay_for(1) == 4
    assert policy.delay_for(2) == 8
    assert policy.delay_for(3) == 16
    assert policy.delay_for(4) == 32
    assert policy.delay_for(5) == 60  # capped at max_delay
    assert policy.delay_for(9) == 60
    assert policy.delay_for(0) == 0.0


def test_backoff_is_configurable():
    policy = BackoffPolicy(base_delay=1, max_delay=5, factor=3)
    assert policy.delay_for(1) == 3
    assert policy.delay_for(2) == 5  # capped at max_delay
    assert policy.delay_for(3) == 5


# --- 3. kill switch ----------------------------------------------------------
def test_emergency_flatten_requires_explicit_authorization(monkeypatch):
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_ENABLED", False)
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", False)
    assert emergency_flatten_authorized(1.0) is False

    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_ENABLED", True)
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", False)
    assert emergency_flatten_authorized(1.0) is False

    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", True)
    assert emergency_flatten_authorized(1.0) is True
    assert emergency_flatten_authorized(0.0) is False


@pytest.mark.asyncio
async def test_kill_switch_cancels_orders_and_does_not_flatten_unless_authorized(
    monkeypatch,
):
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_ENABLED", True)
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", False)

    calls = []

    class FakeEngine:
        connected = True

        async def cancel_all_orders(self, symbol):
            calls.append(("cancel", symbol))

        async def close_position_market(self, symbol):
            calls.append(("flatten", symbol))

    await KillSwitch(FakeEngine(), "ETH/USDT:USDT").apply(0.5)

    assert calls == [("cancel", "ETH/USDT:USDT")]


@pytest.mark.asyncio
async def test_kill_switch_flattens_when_authorized(monkeypatch):
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_ENABLED", True)
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", True)

    calls = []

    class FakeEngine:
        connected = True

        async def cancel_all_orders(self, symbol):
            calls.append(("cancel", symbol))

        async def close_position_market(self, symbol):
            calls.append(("flatten", symbol))

    await KillSwitch(FakeEngine(), "ETH/USDT:USDT").apply(0.5)

    assert calls == [
        ("cancel", "ETH/USDT:USDT"),
        ("flatten", "ETH/USDT:USDT"),
    ]


# --- 4. trade log ------------------------------------------------------------
def test_trade_log_classifies_actions():
    assert TradeLog.classify_action(0.02, 0.0) == "ENTRY / ADD"
    assert TradeLog.classify_action(0.0, 0.02) == "TAKE PROFIT / REDUCE"
    # Equal magnitude with a different sign is a position flip.
    assert TradeLog.classify_action(0.02, -0.02) == "POSITION_UPDATE"
    assert TradeLog.classify_action(0.02, 0.02) == "POSITION_UPDATE"


@pytest.mark.asyncio
async def test_trade_log_writes_the_documented_header(tmp_path):
    path = tmp_path / "trade.csv"
    log = TradeLog(str(path))

    await log.ensure_header()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "Timestamp,Symbol,Action,Position_Size,Entry_Price,Realized_PnL,"
        "Unrealized_PnL,Net_Total_PnL,Wallet_Balance"
    )


@pytest.mark.asyncio
async def test_trade_log_appends_rows(tmp_path):
    path = tmp_path / "trade.csv"
    log = TradeLog(str(path))

    await log.ensure_header()
    await log.record(
        symbol="ETH/USDT:USDT",
        action="ENTRY / ADD",
        position_size=0.01,
        entry_price=2500.0,
        realized_pnl=0.0,
        unrealized_pnl=1.5,
        total_pnl=1.5,
        wallet_balance=10001.5,
    )

    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    fields = rows[1].split(",")
    assert fields[1] == "ETH/USDT:USDT"
    assert fields[2] == "ENTRY / ADD"
    assert float(fields[6]) == 1.5


# --- 5. dashboard routing ----------------------------------------------------
def test_agent_paths_are_parsed():
    assert parse_agent_action("/api/agents/abc/start") == ("abc", "start")
    assert parse_agent_action("/api/agents/abc/delete") == ("abc", "delete")
    assert parse_agent_action("/api/agents/abc/bogus") is None
    assert parse_agent_action("/api/orders") is None
    assert is_agent_collection("/api/agents") is True
    assert is_agent_collection("/api/orders") is False


def test_delete_requires_explicit_confirmation():
    class FakePaper:
        def delete_agent(self, agent_id):
            return {"id": agent_id}

    status, body = dispatch_agent_action(
        FakePaper(), "abc", "delete", {"confirm": "true"}
    )
    assert status == 400
    assert "onay" in body["error"]

    status, body = dispatch_agent_action(
        FakePaper(), "abc", "delete", {"confirm": True}
    )
    assert status == 200
    assert body["agent"]["id"] == "abc"


def test_dashboard_still_serves_the_local_api(tmp_path):
    """The extracted handler must keep the documented HTTP contract."""
    from app import create_server
    from paper_trading import PaperTradingManager

    manager = PaperTradingManager(tmp_path / "paper.json")
    server = create_server(0, manager)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
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

        # Cross-origin requests are still refused.
        request = urllib.request.Request(
            f"{base_url}/api/agents",
            data=json.dumps({"name": "HTTP ajan"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": "http://attacker.example",
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 403

        # Non-JSON requests are still refused.
        request = urllib.request.Request(
            f"{base_url}/api/agents",
            data=b"{}",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 415

        # Unknown routes are still 404.
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{base_url}/api/nope")
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
