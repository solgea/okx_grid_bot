import os
import pytest


def test_g9_refuses_without_demo_mode(monkeypatch):
    monkeypatch.setenv("G9_DEMO_CONFIRM", "true")
    from config.settings import config
    monkeypatch.setattr(config, "IS_DEMO", False)
    monkeypatch.setattr(config, "DRY_RUN", False)
    from scripts.g9_demo_order import main
    with pytest.raises(RuntimeError, match="IS_DEMO"):
        import asyncio
        asyncio.run(main())


def test_g9_refuses_without_explicit_confirmation(monkeypatch):
    monkeypatch.delenv("G9_DEMO_CONFIRM", raising=False)
    from config.settings import config
    monkeypatch.setattr(config, "IS_DEMO", True)
    monkeypatch.setattr(config, "DRY_RUN", False)
    from scripts.g9_demo_order import main
    with pytest.raises(RuntimeError, match="G9_DEMO_CONFIRM"):
        import asyncio
        asyncio.run(main())


# --- verification & cleanup ---------------------------------------------------
import asyncio
import json
from decimal import Decimal

import scripts.g9_demo_order as g9


class FakeExchange:
    def __init__(self, statuses, fail_fetch=0):
        self.statuses = list(statuses)  # successive fetch_order results (dicts)
        self.fail_fetch = fail_fetch
        self.fetch_calls = 0

    async def fetch_order(self, order_id, symbol):
        self.fetch_calls += 1
        if self.fail_fetch > 0:
            self.fail_fetch -= 1
            raise RuntimeError("temporary")
        item = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return dict(item)


class FakeEngine:
    def __init__(self, statuses, cancel_raises=False, fail_fetch=0, position=0.0):
        self.exchange = FakeExchange(statuses, fail_fetch)
        self.cancel_raises = cancel_raises
        self.cancelled = []
        self.placed = []
        self.position = position
        self.closed = False

    async def initialize(self):
        pass

    async def place_order(self, *a, **k):
        self.placed.append((a, k))
        return {"id": "OID1", "status": None}

    async def cancel_order(self, order_id, symbol):
        if self.cancel_raises:
            raise RuntimeError("cancel boom")
        self.cancelled.append(order_id)
        return True

    async def fetch_position(self, symbol):
        return {"size": self.position}

    async def close_connection(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(g9, "VERIFY_DELAY_SEC", 0)


def run(coro):
    return asyncio.run(coro)


def test_open_order_is_canceled_and_confirmed():
    eng = FakeEngine([{"status": "open", "filled": 0}, {"status": "canceled", "filled": 0}])
    obs = run(g9.fetch_order_status(eng, "OID1", "ETH/USDT:USDT"))
    final, code = run(g9.cleanup_order(eng, "OID1", "ETH/USDT:USDT", obs))
    assert code == "CANCELED" and final["status"] == "canceled"
    assert eng.cancelled == ["OID1"]


def test_filled_order_is_not_canceled_and_flagged():
    eng = FakeEngine([{"status": "closed", "filled": 0.01}])
    obs = run(g9.fetch_order_status(eng, "OID1", "ETH/USDT:USDT"))
    final, code = run(g9.cleanup_order(eng, "OID1", "ETH/USDT:USDT", obs))
    assert code == "FILLED_POSITION_OPEN" and eng.cancelled == []


def test_partial_fill_then_cancel_is_flagged_as_position_open():
    eng = FakeEngine([{"status": "open", "filled": 0.005}, {"status": "canceled", "filled": 0.005}])
    obs = run(g9.fetch_order_status(eng, "OID1", "ETH/USDT:USDT"))
    final, code = run(g9.cleanup_order(eng, "OID1", "ETH/USDT:USDT", obs))
    assert code == "FILLED_POSITION_OPEN" and eng.cancelled == ["OID1"]


def test_already_canceled_needs_no_action():
    eng = FakeEngine([{"status": "canceled", "filled": 0}])
    obs = run(g9.fetch_order_status(eng, "OID1", "ETH/USDT:USDT"))
    final, code = run(g9.cleanup_order(eng, "OID1", "ETH/USDT:USDT", obs))
    assert code == "NOT_NEEDED" and eng.cancelled == []


def test_unverified_status_still_attempts_cancel():
    eng = FakeEngine([{"status": "canceled", "filled": 0}], fail_fetch=3)
    obs = run(g9.fetch_order_status(eng, "OID1", "ETH/USDT:USDT"))
    assert obs["status"] == "UNVERIFIED"
    final, code = run(g9.cleanup_order(eng, "OID1", "ETH/USDT:USDT", obs))
    assert eng.cancelled == ["OID1"] and code == "CANCELED"


def test_cancel_failure_is_reported_as_failed():
    eng = FakeEngine([{"status": "open", "filled": 0}], cancel_raises=True)
    obs = run(g9.fetch_order_status(eng, "OID1", "ETH/USDT:USDT"))
    final, code = run(g9.cleanup_order(eng, "OID1", "ETH/USDT:USDT", obs))
    assert code == "FAILED" and "cancel boom" in final["error"]


def _patch_main(monkeypatch, engine):
    from config.settings import config
    from preflight_layer.domain import AccountState, InstrumentMetadata, MarketData
    import time as _t

    monkeypatch.setenv("G9_DEMO_CONFIRM", "true")
    monkeypatch.setattr(config, "IS_DEMO", True)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "API_KEY", "k")
    monkeypatch.setattr(config, "API_SECRET", "s")
    monkeypatch.setattr(config, "PASSPHRASE", "p")
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    monkeypatch.setattr(config, "SYMBOL", "BTC/USDT:USDT")
    monkeypatch.setattr(config, "MAX_POSITION_SIZE", 1.0)

    class FakeAdapter:
        def __init__(self, _engine):
            pass

        async def fetch_instrument_metadata(self, symbol):
            return InstrumentMetadata(symbol=symbol, min_size=Decimal("0.01"), tick_size=Decimal("0.1"),
                                      lot_size=Decimal("0.01"), contract_val=Decimal("0.01"), is_live=True)

        async def fetch_account_state(self):
            return AccountState(balance=Decimal("10000"), available_margin=Decimal("10000"), leverage=Decimal("3"))

        async def fetch_market_data(self, symbol):
            return MarketData(bid=Decimal("60000"), ask=Decimal("60000"), last=Decimal("60000"), timestamp=_t.time())

    monkeypatch.setattr(g9, "OKXEngine", lambda: engine)
    monkeypatch.setattr(g9, "OKXPreFlightAdapter", FakeAdapter)


def test_main_prints_verified_status_and_cancels(monkeypatch, capsys):
    eng = FakeEngine([{"status": "open", "filled": 0}, {"status": "canceled", "filled": 0}])
    _patch_main(monkeypatch, eng)
    run(g9.main())
    evidence = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert evidence["order_id"] == "OID1"
    assert evidence["submit_status"] is None
    assert evidence["status"] == "canceled" and evidence["cleanup"] == "CANCELED"
    assert len(eng.placed) == 1 and eng.cancelled == ["OID1"] and eng.closed


def test_main_raises_but_prints_evidence_when_cleanup_fails(monkeypatch, capsys):
    eng = FakeEngine([{"status": "open", "filled": 0}], cancel_raises=True)
    _patch_main(monkeypatch, eng)
    with pytest.raises(RuntimeError, match="cleanup FAILED"):
        run(g9.main())
    evidence = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert evidence["cleanup"] == "FAILED" and evidence["order_id"] == "OID1"
    assert len(eng.placed) == 1 and eng.closed


def test_main_filled_reports_position_and_does_not_cancel(monkeypatch, capsys):
    eng = FakeEngine([{"status": "closed", "filled": 0.01}], position=0.01)
    _patch_main(monkeypatch, eng)
    run(g9.main())
    out = capsys.readouterr()
    evidence = json.loads(out.out.strip().splitlines()[-1])
    assert evidence["cleanup"] == "FILLED_POSITION_OPEN" and evidence["position_size"] == 0.01
    assert eng.cancelled == [] and "WARNING" in out.err
