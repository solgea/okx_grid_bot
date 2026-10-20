"""Pure mapping from CCXT exchange payloads to PreFlight domain models.

The async OKX adapter and the synchronous Demo panel both need to turn
ccxt market/ticker/balance payloads into the domain objects the PreFlight
rules read. Keeping the mapping here means the two paths cannot disagree
about what "the account leverage is" or "the tick size is".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from preflight_layer.domain import AccountState, InstrumentMetadata, MarketData


def instrument_metadata_from_market(
    symbol: str, market: dict[str, Any]
) -> InstrumentMetadata:
    """Build instrument metadata from a ccxt market payload."""
    raw_info = market.get("info", {}) or {}
    limits = market.get("limits", {}) or {}
    amount_limits = limits.get("amount", {}) or {}
    precision = market.get("precision", {}) or {}

    return InstrumentMetadata(
        symbol=symbol,
        min_size=Decimal(str(raw_info.get("minSz", amount_limits.get("min", 0)))),
        tick_size=Decimal(str(raw_info.get("tickSz", precision.get("price", 0)))),
        lot_size=Decimal(str(raw_info.get("lotSz", precision.get("amount", 0)))),
        contract_val=Decimal(str(raw_info.get("ctVal", "0"))),
        contract_val_ccy=str(raw_info.get("ctValCcy", "")),
        contract_type=str(raw_info.get("ctType", "linear")).lower(),
        is_live=raw_info.get("state", "live") == "live",
    )


def account_state_from_balance(
    balance: dict[str, Any], leverage: Decimal
) -> AccountState:
    """Build account state from a ccxt balance payload."""
    quote = balance.get("USDT", {}) or {}
    return AccountState(
        balance=Decimal(str(quote.get("total", 0.0))),
        available_margin=Decimal(str(quote.get("free", 0.0))),
        leverage=leverage,
    )


def market_data_from_ticker(
    ticker: dict[str, Any], fallback_timestamp: float | None = None
) -> MarketData:
    """Build market data from a ccxt ticker payload.

    The exchange timestamp is used when present. When the exchange does not
    report one, ``fallback_timestamp`` is used so the caller states when
    the price was observed; without it the price is treated as stale and
    PreFlight rejects it.
    """
    last = Decimal(str(ticker.get("last") or 0))
    raw_timestamp = ticker.get("timestamp")
    if raw_timestamp:
        timestamp = float(raw_timestamp) / 1000
    elif fallback_timestamp is not None:
        timestamp = fallback_timestamp
    else:
        timestamp = 0.0
    return MarketData(
        bid=Decimal(str(ticker.get("bid") or last)),
        ask=Decimal(str(ticker.get("ask") or last)),
        last=last,
        timestamp=timestamp,
    )


__all__ = [
    "account_state_from_balance",
    "instrument_metadata_from_market",
    "market_data_from_ticker",
]
