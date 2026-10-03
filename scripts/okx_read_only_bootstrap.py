#!/usr/bin/env python3
"""Deterministic, exchange-read-only OKX Demo bootstrap validation.

This entrypoint intentionally stops after the startup bootstrap. It does not
run main.py and therefore cannot enter the order-sync loop.
"""

import asyncio
import logging

from config.settings import config
from engine.exchange import OKXEngine


FORBIDDEN_MUTATIONS = (
    "set_leverage",
    "set_margin_mode",
    "set_position_mode",
    "create_order",
    "create_orders",
    "cancel_order",
    "cancel_orders",
    "cancel_all_orders",
    "edit_order",
)

EXPECTED_READS = (
    "load_markets",
    "fetch_ticker",
    "fetch_balance",
    "fetch_positions",
    "fetch_open_orders",
)


def _blocked_mutation(name: str):
    async def blocked(*_args, **_kwargs):
        raise AssertionError(
            f"READ_ONLY_VIOLATION: forbidden exchange mutation invoked: {name}"
        )

    return blocked


def _record_read(name: str, original, calls: list[str]):
    async def recorded(*args, **kwargs):
        calls.append(name)
        return await original(*args, **kwargs)

    return recorded


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    )

    if not config.IS_DEMO:
        raise RuntimeError("READ_ONLY_BOOTSTRAP_BLOCKED: IS_DEMO must be true")
    if not config.DRY_RUN:
        raise RuntimeError("READ_ONLY_BOOTSTRAP_BLOCKED: DRY_RUN must be true")

    engine = OKXEngine()
    read_calls: list[str] = []

    try:
        # Instrument the exact exchange instance used by OKXEngine. Any
        # forbidden mutation attempt fails the validation immediately.
        for name in FORBIDDEN_MUTATIONS:
            if hasattr(engine.exchange, name):
                setattr(engine.exchange, name, _blocked_mutation(name))

        for name in EXPECTED_READS:
            original = getattr(engine.exchange, name)
            setattr(
                engine.exchange,
                name,
                _record_read(name, original, read_calls),
            )

        await engine.read_only_bootstrap()

        missing = [name for name in EXPECTED_READS if name not in read_calls]
        if missing:
            raise RuntimeError(
                "READ_ONLY_BOOTSTRAP_INCOMPLETE: missing calls: "
                + ",".join(missing)
            )

        print("OKX_DEMO_READ_ONLY=PASS")
        print(f"SYMBOL={config.SYMBOL}")
        print("IS_DEMO=true")
        print("DRY_RUN=true")
        print("READ_CALLS=" + ",".join(read_calls))
        print("FORBIDDEN_MUTATIONS=NOT_INVOKED")
        print("ORDER_LOOP=NOT_STARTED")
        return 0
    finally:
        await engine.close_connection()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
