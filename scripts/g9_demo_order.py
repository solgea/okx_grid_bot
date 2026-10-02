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


async def main():
    if not config.IS_DEMO:
        raise RuntimeError("G9 refuses to run unless IS_DEMO=true")
    if config.DRY_RUN:
        raise RuntimeError("G9 requires DRY_RUN=false for the real Demo submission")
    if os.getenv("G9_DEMO_CONFIRM") != "true":
        raise RuntimeError("G9 requires G9_DEMO_CONFIRM=true")
    if not config.API_KEY or not config.API_SECRET or not config.PASSPHRASE:
        raise RuntimeError("G9 requires OKX Demo API credentials")

    engine = OKXEngine()
    try:
        await engine.initialize()
        metadata = await __import__("adapters.okx_adapter", fromlist=["OKXPreFlightAdapter"]).OKXPreFlightAdapter(engine).fetch_instrument_metadata(config.SYMBOL)
        balance = await engine.fetch_balance()
        price = await engine.fetch_current_price(config.SYMBOL)
        if not price or price <= 0:
            raise RuntimeError("G9 market price unavailable")

        # One deliberately tiny, one-shot limit order just below market.
        raw_price = Decimal(str(price))
        tick = metadata.tick_size
        order_price = (raw_price / tick).to_integral_value() * tick - tick
        size = max(metadata.min_size, metadata.lot_size)
        account = AccountState(
            balance=Decimal(str(balance)),
            available_margin=Decimal(str(balance)),
            leverage=Decimal(str(config.LEVERAGE)),
        )
        market = MarketData(
            bid=raw_price, ask=raw_price, last=raw_price, timestamp=time.time()
        )
        intent = OrderIntent(
            instrument_id=metadata.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=order_price,
            size=size,
            leverage=Decimal(str(config.LEVERAGE)),
            margin_mode=config.MARGIN_MODE,
            position_side="net",
            reduce_only=False,
            client_order_id="g9-demo-once",
        )
        validator = PreFlightValidator()
        result = validator.validate(intent, metadata, account, market)
        if not result.passed or validator.state.value != "AUTHORIZED":
            raise RuntimeError(f"G9 preflight rejected: {result.rejection_code} {result.message}")

        order = await engine.place_order(
            config.SYMBOL, "buy", float(size), float(order_price), "limit",
            params={"tdMode": config.MARGIN_MODE, "clOrdId": "g9-demo-once"},
        )
        evidence = {
            "gate": "G9",
            "mode": "DEMO",
            "symbol": config.SYMBOL,
            "preflight": "AUTHORIZED",
            "order_id": order.get("id"),
            "status": order.get("status"),
            "timestamp": time.time(),
        }
        if not evidence["order_id"]:
            raise RuntimeError("G9 exchange response did not contain an order id")
        print(json.dumps(evidence, sort_keys=True))
    finally:
        await engine.close_connection()


if __name__ == "__main__":
    asyncio.run(main())
