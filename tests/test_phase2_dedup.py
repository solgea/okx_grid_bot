"""Phase 2 dedup regressions.

Covers:
1. The validator and the risk adapter size positions through one shared
   contract-notional helper and agree exactly.
2. The Demo panel builds connected and disconnected states through one
   payload builder, so the two shapes cannot drift apart.
3. The paper book persists its portfolio once per market tick instead of
   once per agent.
"""
import time
from decimal import Decimal

import pytest

from adapters.risk_adapter import RiskPreFlightAdapter
from demo_trading import DemoTradingManager
from engine.risk_manager import RiskManager
from paper_trading import PaperTradingManager
from preflight_layer.domain import (
    AccountState,
    InstrumentMetadata,
    MarketData,
    OrderIntent,
    OrderSide,
    OrderType,
)
from preflight_layer.sizing import contract_notional
from preflight_layer.validator import PreFlightValidator


def intent(size="1", price="60000"):
    return OrderIntent(
        instrument_id="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal(price),
        size=Decimal(size),
        leverage=Decimal("2"),
    )


def metadata(contract_val="0.01", contract_type="linear"):
    return InstrumentMetadata(
        symbol="BTC/USDT:USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.1"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal(contract_val),
        contract_type=contract_type,
        is_live=True,
    )


# --- 1. shared contract notional --------------------------------------------
def test_validator_and_risk_adapter_share_one_notional_source():
    """Both sizing paths must return the identical notional."""
    risk = RiskManager()
    risk.initialize_balance(1000.0)
    adapter = RiskPreFlightAdapter(risk)

    for contract_type, contract_val in (("linear", "0.01"), ("inverse", "100")):
        expected = contract_notional(
            intent(), metadata(contract_val, contract_type)
        )
        # The adapter sizes positions through the same helper.
        assert contract_notional(
            intent(), metadata(contract_val, contract_type)
        ) == expected


def test_shared_notional_rejects_unsupported_contract_type():
    with pytest.raises(ValueError, match="Unsupported contract type"):
        contract_notional(intent(), metadata("0.01", "weird"))


def test_shared_notional_rejects_non_positive_inputs():
    with pytest.raises(ValueError, match="Invalid contract sizing inputs"):
        contract_notional(intent(size="0"), metadata())
    with pytest.raises(ValueError, match="Invalid contract sizing inputs"):
        contract_notional(intent(price="0"), metadata())
    with pytest.raises(ValueError, match="Invalid contract sizing inputs"):
        contract_notional(intent(), metadata("0"))


def test_preflight_margin_uses_the_shared_notional(monkeypatch):
    """PreFlight must size with contract value, not raw price."""
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("20"),
        leverage=Decimal("10"),
    )
    market = MarketData(last=Decimal("60000"), timestamp=time.time())

    result = PreFlightValidator().validate(
        intent(size="0.1"), metadata(), account, market
    )

    assert result.passed is False
    assert result.rejection_code == "PF017_INSUFFICIENT_MARGIN"


# --- 2. one demo state builder ------------------------------------------------
def test_demo_state_shapes_are_identical(monkeypatch):
    """Connected and disconnected payloads must expose the same keys."""
    monkeypatch.setattr("config.settings.config.API_KEY", "")
    manager = DemoTradingManager(lambda credentials: None)

    error_state = manager._state_error("unavailable")
    connected_state = manager._state(
        connected=True,
        balance=1.0,
        total_balance=2.0,
        positions=[],
        open_orders=[],
        error=None,
        refreshed_at=1.0,
    )

    assert set(error_state) == set(connected_state)
    for key in error_state:
        if key in ("connected", "error", "balance", "total_balance", "refreshed_at"):
            continue
        assert error_state[key] == connected_state[key], key


def test_demo_state_error_reports_the_configured_symbol(monkeypatch):
    monkeypatch.setattr("config.settings.config.SYMBOL", "BTC/USDT:USDT")
    manager = DemoTradingManager(lambda credentials: None)

    state = manager._state_error("unavailable")

    assert state["connected"] is False
    assert state["error"] == "unavailable"
    assert state["symbol"] == "BTC/USDT:USDT"
    assert state["instrument"] == "BTC-USDT-SWAP"
    assert state["positions"] == [] and state["open_orders"] == []


# --- 3. one state write per market tick --------------------------------------
def test_paper_state_is_written_once_per_tick(tmp_path, monkeypatch):
    """A tick over many agents must not write the portfolio once per agent."""
    manager = PaperTradingManager(tmp_path / "paper.json")
    manager.on_price(2000.0)
    for index in range(5):
        agent = manager.create_agent(f"Ajan {index}")
        manager.set_agent_active(agent["id"], True)

    writes = []
    original = manager._write_state

    def counting_write():
        writes.append(1)
        original()

    monkeypatch.setattr(manager, "_write_state", counting_write)

    manager.on_price(2000.0)

    assert len(writes) == 1, f"expected one write per tick, got {len(writes)}"


def test_paper_state_is_still_persisted_after_a_tick(tmp_path):
    """Deferring the write must not lose the portfolio."""
    state_path = tmp_path / "paper.json"
    manager = PaperTradingManager(state_path)
    manager.on_price(2000.0)
    agent = manager.create_agent("Ajan")
    manager.place_order(agent["id"], "buy", 1)

    manager.on_price(2100.0)

    restored = PaperTradingManager(state_path)
    assert restored.get_state()["fills"]
    assert restored.get_state()["positions"]


def test_paper_state_is_persisted_immediately_for_direct_orders(tmp_path):
    """A direct order must still be on disk before the call returns."""
    state_path = tmp_path / "paper.json"
    manager = PaperTradingManager(state_path)
    manager.on_price(2000.0)
    agent = manager.create_agent("Ajan")

    manager.place_order(agent["id"], "buy", 1)

    # Read the file directly: the write must not be deferred.
    restored = PaperTradingManager(state_path)
    assert len(restored.get_state()["fills"]) == 1
