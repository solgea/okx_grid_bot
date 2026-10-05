from decimal import Decimal

from adapters.risk_adapter import RiskPreFlightAdapter
from engine.risk_manager import RiskManager
from preflight_layer.domain import OrderIntent, OrderSide, OrderType


def test_missing_friction_target_fails_closed():
    risk = RiskManager()
    adapter = RiskPreFlightAdapter(risk)
    intent = OrderIntent(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("2500"),
        size=Decimal("0.01"),
    )

    assert adapter.validate_friction(intent) is False


def test_valid_friction_target_is_evaluated():
    risk = RiskManager()
    adapter = RiskPreFlightAdapter(risk)
    intent = OrderIntent(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("2500"),
        size=Decimal("0.01"),
    )
    intent.expected_target_price = Decimal("2600")

    assert adapter.validate_friction(intent) is True
