"""Offline validation of the configured symbol.

The previous version of this test called the live OKX API and asserted
nothing, so it passed even when the symbol was invalid and it made the test
suite depend on network access. These checks are deterministic and offline.
"""
import pytest

from config.settings import config, to_native_symbol
from preflight_layer.sizing import contract_notional
from preflight_layer.domain import InstrumentMetadata, OrderIntent, OrderSide, OrderType
from decimal import Decimal


def test_configured_symbol_is_a_unified_swap_symbol():
    """SYMBOL must be a unified BASE/QUOTE:SETTLE contract."""
    base, separator, remainder = config.SYMBOL.partition("/")
    quote, settle_separator, settle = remainder.partition(":")

    assert separator, f"{config.SYMBOL} must contain '/'"
    assert base
    assert quote
    assert settle_separator, f"{config.SYMBOL} must be a swap symbol with a settle currency"
    assert settle


def test_native_symbol_derives_from_the_configured_symbol():
    """The native OKX instrument id must follow the configured symbol."""
    native = to_native_symbol(config.SYMBOL)
    base = config.SYMBOL.partition("/")[0]
    quote = config.SYMBOL.partition("/")[2].partition(":")[0]

    assert native == f"{base}-{quote}-SWAP"


def test_contract_notional_matches_the_configured_symbol():
    """A one-contract order must be sized from the configured instrument."""
    metadata = InstrumentMetadata(
        symbol=config.SYMBOL,
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("0.01"),
        contract_type="linear",
        is_live=True,
    )
    intent = OrderIntent(
        instrument_id=config.SYMBOL,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("100"),
        size=Decimal("1"),
        leverage=Decimal("1"),
    )

    # 1 contract × 0.01 base × 100 quote = 1 quote unit.
    assert contract_notional(intent, metadata) == Decimal("1.00")


def test_invalid_symbols_are_rejected():
    for bad in ("ETHUSDT", "ETH/", "/USDT:USDT", ""):
        with pytest.raises(ValueError):
            to_native_symbol(bad)
