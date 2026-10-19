"""Market data consumption and SMC analysis for the grid bot.

Consumes the native OKX websocket stream, derives Smart Money Concepts from
confirmed candles, and publishes the result to the shared market state. The
grid is updated here exactly once per analysis.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

import pandas_ta_classic as ta

from bot.market_state import MarketState
from strategy.grid_engine import GridEngine
from strategy.smc_engine import SMCVolumeEngine

logger = logging.getLogger("MarketConsumer")

CANDLE_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
]
MIN_CANDLES_FOR_STRUCTURE = 3
CANDLE_HISTORY = 100


class MarketConsumer:
    """Consume market events and keep the grid aligned with the market."""

    def __init__(
        self,
        adapter: Any,
        smc: SMCVolumeEngine,
        grid: GridEngine,
        state: MarketState,
    ) -> None:
        self.adapter = adapter
        self.smc = smc
        self.grid = grid
        self.state = state

    async def run(self, symbol: str, timeframe: str) -> None:
        """Consume market events until the task is cancelled."""
        candles: deque[Any] = deque(maxlen=CANDLE_HISTORY)
        async for event in self.adapter.market_events(symbol, timeframe):
            try:
                await self.state.update_price(event.price)
                if event.ohlcv and event.confirmed:
                    candles.append(event.ohlcv)
                    await self._analyze_candles(candles, event.price)
            finally:
                self._release_event(event)

    async def _analyze_candles(self, candles: deque[Any], price: float) -> None:
        """Derive SMC data from the candle history and update the grid."""
        frame = ta.DataFrame(
            list(candles),
            columns=CANDLE_COLUMNS,
        )
        if len(frame) < MIN_CANDLES_FOR_STRUCTURE:
            return

        smc_data = {
            "volume_profile": self.smc.analyze_volume_profile(frame),
            "order_blocks": self.smc.identify_order_blocks(frame),
            **self.smc.analyze_structure(frame),
        }
        confluence = self.smc.calculate_confluence(
            frame,
            smc_data,
            smc_data["volume_profile"],
        )
        smc_data["confluence_score"] = confluence.score
        self.smc.confluence_pool.release(confluence)

        await self.state.publish_smc(smc_data, confluence.score)
        self.grid.update_grid_from_smc(smc_data, price)

    def _release_event(self, event: Any) -> None:
        """Return the pooled event so it can be reused."""
        if not event:
            return
        stream = getattr(self.adapter, "market_stream", None)
        pool = getattr(stream, "pool", None)
        if pool:
            pool.release(event)


async def sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep, but wake early when the bot is asked to stop."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


__all__ = ["MarketConsumer", "sleep_or_stop"]
