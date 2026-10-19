"""Runtime components for the OKX grid bot.

The package is split so that each concern lives in one place:

- ``bot.market_state``  - shared market snapshot between the stream consumer
  and the trading loop.
- ``bot.market_consumer`` - websocket consumption and SMC analysis.
- ``bot.trading_loop``  - the order reconciliation cycle.
- ``bot.kill_switch``   - emergency flatten and halt decisions.
- ``bot.backoff``       - retry policy for transient exchange errors.
- ``bot.trade_log``     - the CSV trade journal.
"""

from bot.market_state import MarketState
from bot.trade_log import TradeLog

__all__ = ["MarketState", "TradeLog"]
