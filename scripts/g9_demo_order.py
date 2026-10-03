import asyncio
import json
import os
import sys
import time
from decimal import Decimal

from config.settings import config
from engine.exchange import OKXEngine
from preflight_layer.domain import AccountState, MarketData, OrderIntent, OrderSide, OrderType
from preflight_layer.validator import PreFlightValidator
from adapters.okx_adapter import OKXPreFlightAdapter


TERMINAL_STATES = {"closed", "canceled", "expired", "rejected"}
VERIFY_ATTEMPTS = 3
VERIFY_DELAY_SEC = 1.0


async def fetch_order_status(engine, order_id, symbol):
    """Read the order's real state from the exchange (read-only).

    The submit response often carries no status, so the status is verified
    with fetch_order. Returns status "UNVERIFIED" if it cannot be read.
    """
    last_error = None
    for attempt in range(VERIFY_ATTEMPTS):
        try:
            order = await engine.exchange.fetch_order(order_id, symbol)
            status = (order or {}).get("status")
            if status:
                return {"status": status, "filled": float(order.get("filled") or 0.0), "error": None}
        except Exception as exc:  # noqa: BLE001 - reported in evidence
            last_error = repr(exc)
        if attempt < VERIFY_ATTEMPTS - 1:
            await asyncio.sleep(VERIFY_DELAY_SEC)
    return {"status": "UNVERIFIED", "filled": None, "error": last_error}


async def cleanup_order(engine, order_id, symbol, observed):
    """Cancel the one G9 order if it is still working. Never submits orders.

    Returns (final_observation, cleanup_code):
      NOT_NEEDED            already canceled/expired/rejected
      CANCELED              cancel confirmed by the exchange
      FILLED_POSITION_OPEN  order filled (fully or partly); position is NOT
                            auto-closed, close it manually in the Demo UI
      FAILED                order may still be open; manual action required
    """
    status = observed["status"]
    if status in TERMINAL_STATES:
        filled = (observed.get("filled") or 0) > 0
        return observed, ("FILLED_POSITION_OPEN" if status == "closed" or filled else "NOT_NEEDED")

    cancel_error = None
    try:
        await engine.cancel_order(order_id, symbol)
    except Exception as exc:  # noqa: BLE001 - verified below, reported in evidence
        cancel_error = repr(exc)

    final = await fetch_order_status(engine, order_id, symbol)
    if cancel_error and not final.get("error"):
        final["error"] = cancel_error
    if final["status"] == "closed" or (final.get("filled") or 0) > 0:
        return final, "FILLED_POSITION_OPEN"
    if final["status"] == "canceled":
        return final, "CANCELED"
    return final, "FAILED"


async def main():
    if not config.IS_DEMO:
        raise RuntimeError("G9 refuses to run unless IS_DEMO=true")
    if config.DRY_RUN:
        raise RuntimeError("G9 requires DRY_RUN=false for the real Demo submission")
    if os.getenv("G9_DEMO_CONFIRM") != "true":
        raise RuntimeError("G9 requires G9_DEMO_CONFIRM=true")
    if not config.API_KEY or not config.API_SECRET or not config.PASSPHRASE:
        raise RuntimeError("G9 requires OKX Demo API credentials")

    # G9 is an isolated, one-shot Demo gate. The normal bot kill switch
    # remains enabled globally; only this dedicated process may authorize
    # its single explicitly confirmed Demo order.
    if config.KILL_SWITCH_ACTIVE:
        config.KILL_SWITCH_ACTIVE = False

    engine = OKXEngine()
    try:
        await engine.initialize()
        adapter = OKXPreFlightAdapter(engine)
        metadata = await adapter.fetch_instrument_metadata(config.SYMBOL)
        account = await adapter.fetch_account_state()
        market = await adapter.fetch_market_data(config.SYMBOL)

        if market.last <= 0:
            raise RuntimeError("G9 market price unavailable")

        # One deliberately tiny, one-shot BUY LIMIT order below market.
        raw_price = market.last
        tick = metadata.tick_size
        order_price = (raw_price / tick).to_integral_value() * tick - tick
        if order_price <= 0:
            raise RuntimeError("G9 calculated an invalid order price")

        size = max(metadata.min_size, metadata.lot_size)
        intent = OrderIntent(
            instrument_id=metadata.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=order_price,
            size=size,
            leverage=account.leverage,
            margin_mode=config.MARGIN_MODE,
            position_side="net",
            reduce_only=False,
            client_order_id="g9demo01",
        )

        validator = PreFlightValidator()
        result = validator.validate(intent, metadata, account, market)
        if not result.passed or validator.state.value != "AUTHORIZED":
            raise RuntimeError(
                f"G9 preflight rejected: {result.rejection_code} {result.message}"
            )

        order = await engine.place_order(
            config.SYMBOL,
            "buy",
            float(size),
            float(order_price),
            "limit",
            params={"tdMode": config.MARGIN_MODE, "clOrdId": "g9demo01"},
        )

        order_id = order.get("id")
        if not order_id:
            raise RuntimeError("G9 exchange response did not contain an order id")

        observed = await fetch_order_status(engine, order_id, config.SYMBOL)
        final, cleanup = await cleanup_order(engine, order_id, config.SYMBOL, observed)

        position_size = None
        if (final.get("filled") or 0) > 0 or cleanup == "FILLED_POSITION_OPEN":
            try:
                position_size = (await engine.fetch_position(config.SYMBOL)).get("size")
            except Exception:  # noqa: BLE001 - best effort, evidence only
                position_size = "UNKNOWN"

        evidence = {
            "gate": "G9",
            "mode": "DEMO",
            "symbol": config.SYMBOL,
            "preflight": "AUTHORIZED",
            "order_id": order_id,
            "submit_status": order.get("status"),
            "status": final["status"],
            "filled": final.get("filled"),
            "cleanup": cleanup,
            "position_size": position_size,
            "verify_error": final.get("error"),
            "timestamp": time.time(),
        }
        print(json.dumps(evidence, sort_keys=True))
        if cleanup == "FAILED":
            raise RuntimeError(
                f"G9 cleanup FAILED: order {order_id} may still be open; cancel it manually in the OKX Demo UI"
            )
        if cleanup == "FILLED_POSITION_OPEN":
            print(
                f"WARNING: G9 order {order_id} filled; close the Demo position manually.",
                file=sys.stderr,
            )
    finally:
        await engine.close_connection()


if __name__ == "__main__":
    asyncio.run(main())
