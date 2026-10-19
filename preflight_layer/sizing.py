"""Shared contract sizing for the PreFlight layer.

Single source of truth for converting an order intent into quote-currency
notional. Both the PreFlight validator and the risk adapter size positions
this way, so they must agree exactly.
"""

from decimal import Decimal

from preflight_layer.domain import InstrumentMetadata, OrderIntent


def contract_notional(intent: OrderIntent, metadata: InstrumentMetadata) -> Decimal:
    """Return the quote-currency notional for a linear/inverse OKX contract.

    Linear contracts are sized as contracts * contract_value * price.
    Inverse contracts are sized as contracts * contract_value / price.

    Raises ValueError for non-positive sizing inputs or an unsupported
    contract type, so callers fail closed rather than sizing an order with a
    silently wrong value.
    """
    contracts = intent.size
    price = intent.price
    contract_value = metadata.contract_val
    if contracts <= 0 or price <= 0 or contract_value <= 0:
        raise ValueError("Invalid contract sizing inputs")
    contract_type = metadata.contract_type.lower()
    if contract_type == "linear":
        return contracts * contract_value * price
    if contract_type == "inverse":
        return contracts * contract_value / price
    raise ValueError(f"Unsupported contract type: {metadata.contract_type}")
