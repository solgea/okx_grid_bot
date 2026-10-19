"""The CSV trade journal for the grid bot.

Rows are appended asynchronously so the trading loop is never blocked by a
disk write, and the file is created with a header row on first use.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import aiofiles

TRADE_LOG_FILE = "trade_execution_log.csv"
TRADE_LOG_HEADERS = [
    "Timestamp",
    "Symbol",
    "Action",
    "Position_Size",
    "Entry_Price",
    "Realized_PnL",
    "Unrealized_PnL",
    "Net_Total_PnL",
    "Wallet_Balance",
]

ENTRY_ACTION = "ENTRY / ADD"
REDUCE_ACTION = "TAKE PROFIT / REDUCE"
UPDATE_ACTION = "POSITION_UPDATE"
PNL_CHANGE_THRESHOLD = 0.05


class TradeLog:
    """Append-only journal of position and PnL changes."""

    def __init__(self, path: str = TRADE_LOG_FILE) -> None:
        self.path = path

    async def ensure_header(self) -> None:
        """Create the journal with a header row if it does not exist yet."""
        if os.path.exists(self.path):
            return
        await self._append(TRADE_LOG_HEADERS)

    async def _append(self, row_data: list[Any]) -> None:
        line = ",".join(map(str, row_data)) + "\n"
        async with aiofiles.open(self.path, mode="a", newline="") as handle:
            await handle.write(line)

    @staticmethod
    def classify_action(
        current_position_size: float, last_position_size: float
    ) -> str:
        """Return the journal action for a position-size change."""
        if abs(current_position_size) > abs(last_position_size):
            return ENTRY_ACTION
        if abs(current_position_size) < abs(last_position_size):
            return REDUCE_ACTION
        return UPDATE_ACTION

    async def record(
        self,
        *,
        symbol: str,
        action: str,
        position_size: float,
        entry_price: float,
        realized_pnl: float,
        unrealized_pnl: float,
        total_pnl: float,
        wallet_balance: float,
    ) -> None:
        """Append one journal row describing the current account state."""
        await self._append(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                action,
                position_size,
                round(entry_price, 4) if entry_price else 0.0,
                round(realized_pnl, 4),
                round(unrealized_pnl, 4),
                round(total_pnl, 4),
                round(wallet_balance, 4),
            ]
        )
