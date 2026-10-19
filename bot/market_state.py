"""Shared market snapshot for the market consumer and the trading loop.

The websocket consumer and the trading loop run as separate asyncio tasks.
Previously they shared a plain dict, which allowed the loop to consume and
clear ``smc_data`` that the consumer had just produced, and applied the
same SMC update to the grid twice with different prices.

``MarketState`` keeps a single pending SMC payload and hands it to exactly
one consumer, so an update is applied once and never dropped.
"""

from __future__ import annotations

import asyncio
from typing import Any


class MarketState:
    """Latest market price plus the newest pending SMC analysis."""

    def __init__(self) -> None:
        self._price: float | None = None
        self._confluence_score: int | None = None
        self._pending_smc: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    @property
    def price(self) -> float | None:
        return self._price

    @property
    def confluence_score(self) -> int | None:
        return self._confluence_score

    async def update_price(self, price: float) -> None:
        async with self._lock:
            self._price = price

    async def publish_smc(
        self, smc_data: dict[str, Any], confluence_score: int | None
    ) -> None:
        """Record a fresh SMC analysis for the trading loop to consume."""
        async with self._lock:
            self._pending_smc = smc_data
            self._confluence_score = confluence_score

    async def take_pending_smc(self) -> dict[str, Any] | None:
        """Return the pending SMC analysis and clear it.

        Only one caller can receive a given payload, so the grid is updated
        once per analysis and no analysis is applied twice.
        """
        async with self._lock:
            smc_data = self._pending_smc
            self._pending_smc = None
            return smc_data

    async def restore_smc(self, smc_data: dict[str, Any] | None) -> None:
        """Seed the state with a restored SMC payload from a previous run."""
        async with self._lock:
            self._pending_smc = smc_data
