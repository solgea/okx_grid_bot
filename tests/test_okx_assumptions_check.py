import asyncio
import inspect
import re

import pytest

from scripts import okx_demo_assumptions_check as chk


class FakeExchange:
    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def market(self, symbol):
        return {"id": "ETH-USDT-SWAP"}

    async def _get(self, name, payload):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError("boom secret-key")
        return payload

    async def privateGetAccountConfig(self, p): return await self._get("config", {"data": [{"posMode": "net_mode", "acctLv": "2"}]})
    async def publicGetPublicInstruments(self, p): return await self._get("inst", {"data": [{"tickSz": "0.01", "lotSz": "0.01", "minSz": "0.01", "ctVal": "0.1", "ctMult": "1", "state": "live"}]})
    async def privateGetTradeOrdersAlgoPending(self, p): return await self._get("algo", {"data": []})
    async def privateGetAccountTradeFee(self, p): return await self._get("fee", {"data": [{"maker": "-0.0002", "taker": "-0.0005"}]})
    async def privateGetTradeFills(self, p): return await self._get("fills", {"data": []})
    async def privateGetAccountBills(self, p): return await self._get("bills", {"data": []})
    async def publicGetPublicFundingRate(self, p): return await self._get("fr", {"data": [{"fundingRate": "0.0001", "nextFundingTime": "1"}]})
    # mutating surface that must be blocked
    def privatePostTradeOrder(self, p): self.calls.append("MUTATION"); return {}
    def create_order(self, *a): self.calls.append("MUTATION"); return {}


def run(coro):
    return asyncio.run(coro)


def test_cl_ord_id_rule_matches_contract():
    assert chk.validate_cl_ord_id("gab12cd34ef567")
    assert not chk.validate_cl_ord_id("1abc")               # must start with a letter
    assert not chk.validate_cl_ord_id("a" * 33)              # <= 32
    assert not chk.validate_cl_ord_id("ab-12") and not chk.validate_cl_ord_id("")


def test_harden_blocks_every_mutation_and_keeps_reads():
    ex = FakeExchange()
    blocked = chk.harden(ex)
    assert "privatePostTradeOrder" in blocked and "create_order" in blocked
    with pytest.raises(AssertionError, match="READ_ONLY_VIOLATION"):
        ex.privatePostTradeOrder({})
    with pytest.raises(AssertionError, match="READ_ONLY_VIOLATION"):
        ex.create_order("x")
    assert run(ex.privateGetAccountConfig({}))["data"][0]["posMode"] == "net_mode"
    assert "MUTATION" not in ex.calls


def test_run_checks_reports_values_and_marks_unprovable_items():
    ex = FakeExchange(); chk.harden(ex)
    res = run(chk.run_checks(ex, "ETH/USDT:USDT"))
    assert res["pos_mode"]["posMode"] == "net_mode" and res["instrument"]["tickSz"] == "0.01"
    assert res["fee_rates"]["taker"] == "-0.0005" and res["algo_pending_query"]["pending_conditional_orders"] == 0
    assert res["fills_fee_fields"]["status"] == "NO_DATA" and res["funding_bills"]["status"] == "NO_DATA"
    for key in ("attach_algo_orders", "reduce_only", "duplicate_cl_ord_id_behavior", "demo_supports_attached_sl"):
        assert res[key]["status"] == "UNVERIFIED_READ_ONLY"
    assert chk.summarize(res)["failed"] == []


def test_failures_are_isolated_and_secrets_are_scrubbed():
    ex = FakeExchange(fail={"algo"}); chk.harden(ex)
    res = run(chk.run_checks(ex, "ETH/USDT:USDT", secrets=("secret-key",)))
    assert res["algo_pending_query"]["status"] == "FAIL" and "secret-key" not in res["algo_pending_query"]["detail"]
    assert res["pos_mode"]["status"] == "OK"                 # other checks still ran
    assert chk.summarize(res)["failed"] == ["algo_pending_query"]


def test_script_only_calls_get_endpoints():
    src = inspect.getsource(chk.run_checks)
    called = set(re.findall(r"exchange\.(\w+)\(", src))
    called.discard("market")
    assert called and all(name.startswith(chk.ALLOWED_PREFIXES) for name in called), called
