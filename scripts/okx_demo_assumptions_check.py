#!/usr/bin/env python3
"""Read-only verification of the OKX Demo assumptions in docs/DEMO_EXECUTION_CONTRACT.md (section 11).

Only GET endpoints are called (ccxt ``publicGet*`` / ``privateGet*``). Every
mutating ccxt method is replaced with a blocker before any request is made.
Assumptions that cannot be proven without placing an order are reported as
UNVERIFIED_READ_ONLY and must be proven in the first controlled Phase B run.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from typing import Any

FORBIDDEN_EXACT = (
    "set_leverage", "set_margin_mode", "set_position_mode", "create_order", "create_orders",
    "cancel_order", "cancel_orders", "cancel_all_orders", "edit_order", "close_position",
)
ALLOWED_PREFIXES = ("publicGet", "privateGet")
CLORDID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,31}$")  # letter first, alphanumeric, <= 32


def validate_cl_ord_id(value: str) -> bool:
    """Contract rule: 1-32 case-sensitive alphanumerics, starting with a letter."""
    return bool(CLORDID_RE.fullmatch(value))


def _blocked(name: str):
    def blocked(*_a, **_k):
        raise AssertionError(f"READ_ONLY_VIOLATION: {name}")
    return blocked


def harden(exchange: Any) -> list[str]:
    """Replace every non-GET exchange API call with a blocker; return blocked names."""
    blocked: list[str] = []
    for name in dir(exchange):
        if name in FORBIDDEN_EXACT or re.match(r"^(private|public)(Post|Put|Delete|Patch)", name):
            setattr(exchange, name, _blocked(name))
            blocked.append(name)
    return blocked


def _row(response: Any) -> dict[str, Any]:
    data = (response or {}).get("data") or []
    return data[0] if data else {}


async def _check(name: str, fn, results: dict[str, Any], secrets: tuple[str, ...]) -> None:
    try:
        results[name] = await fn()
    except Exception as exc:  # noqa: BLE001 - reported as evidence
        message = str(exc)[:160]
        for secret in secrets:
            if secret:
                message = message.replace(secret, "***")
        results[name] = {"status": "FAIL", "error": type(exc).__name__, "detail": message}


async def run_checks(exchange: Any, symbol: str, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    market = exchange.market(symbol)
    inst_id = market["id"]
    results: dict[str, Any] = {"inst_id": inst_id}

    async def position_mode():
        row = _row(await exchange.privateGetAccountConfig({}))
        mode = row.get("posMode")
        return {"status": "OK" if mode else "FAIL", "posMode": mode, "acctLv": row.get("acctLv")}

    async def instrument():
        row = _row(await exchange.publicGetPublicInstruments({"instType": "SWAP", "instId": inst_id}))
        keys = ("tickSz", "lotSz", "minSz", "ctVal", "ctMult", "state")
        return {"status": "OK" if row else "FAIL", **{k: row.get(k) for k in keys}}

    async def algo_pending():
        data = (await exchange.privateGetTradeOrdersAlgoPending({"ordType": "conditional", "instType": "SWAP"})).get("data")
        return {"status": "OK", "query": "reachable", "pending_conditional_orders": len(data or [])}

    async def fee_rates():
        row = _row(await exchange.privateGetAccountTradeFee({"instType": "SWAP", "instId": inst_id}))
        return {"status": "OK" if row else "FAIL", "maker": row.get("maker"), "taker": row.get("taker")}

    async def fills_fee_fields():
        data = (await exchange.privateGetTradeFills({"instType": "SWAP", "limit": "5"})).get("data") or []
        if not data:
            return {"status": "NO_DATA", "note": "no fills yet; fee fields unproven until a fill exists"}
        return {"status": "OK", "has_fee": "fee" in data[0], "has_feeCcy": "feeCcy" in data[0]}

    async def funding_bills():
        data = (await exchange.privateGetAccountBills({"instType": "SWAP", "type": "8", "limit": "5"})).get("data") or []
        if not data:
            return {"status": "NO_DATA", "query": "reachable", "note": "no funding bills yet"}
        return {"status": "OK", "fields": sorted(data[0].keys())}

    async def funding_rate():
        row = _row(await exchange.publicGetPublicFundingRate({"instId": inst_id}))
        return {"status": "OK" if row else "FAIL", "has_fundingRate": "fundingRate" in row,
                "has_nextFundingTime": "nextFundingTime" in row}

    for name, fn in (("pos_mode", position_mode), ("instrument", instrument), ("algo_pending_query", algo_pending),
                     ("fee_rates", fee_rates), ("fills_fee_fields", fills_fee_fields),
                     ("funding_bills", funding_bills), ("funding_rate", funding_rate)):
        await _check(name, fn, results, secrets)

    results["cl_ord_id_rule"] = {
        "status": "DOC_ONLY", "rule": "1-32 case-sensitive alphanumerics, start with a letter",
        "example_ok": validate_cl_ord_id("gab12cd34ef567"), "example_digit_first_rejected": not validate_cl_ord_id("1abc"),
    }
    for name in ("attach_algo_orders", "reduce_only", "duplicate_cl_ord_id_behavior", "demo_supports_attached_sl"):
        results[name] = {"status": "UNVERIFIED_READ_ONLY", "prove_in": "first controlled Phase B run"}
    return results


def summarize(results: dict[str, Any]) -> dict[str, Any]:
    statuses = {k: v.get("status") for k, v in results.items() if isinstance(v, dict)}
    return {"failed": sorted(k for k, s in statuses.items() if s == "FAIL"),
            "unverified": sorted(k for k, s in statuses.items() if s in ("UNVERIFIED_READ_ONLY", "NO_DATA", "DOC_ONLY"))}


async def main() -> int:
    from config.settings import config
    from engine.exchange import OKXEngine

    if not config.IS_DEMO:
        raise RuntimeError("ASSUMPTION_CHECK_BLOCKED: IS_DEMO must be true")
    engine = OKXEngine()
    try:
        harden(engine.exchange)
        await engine.exchange.load_markets()
        results = await run_checks(engine.exchange, config.SYMBOL, (config.API_KEY, config.API_SECRET, config.PASSPHRASE))
        summary = summarize(results)
        print(json.dumps({"mode": "DEMO_READ_ONLY", "symbol": config.SYMBOL, "timestamp": time.time(),
                          "results": results, "summary": summary}, sort_keys=True, indent=2))
        return 1 if summary["failed"] else 0
    finally:
        await engine.close_connection()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
