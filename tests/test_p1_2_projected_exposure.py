from decimal import Decimal

from adapters.risk_adapter import RiskPreFlightAdapter
from engine.risk_manager import RiskManager
from preflight_layer.domain import AccountState, InstrumentMetadata, OrderIntent, OrderSide, OrderType


def make_metadata():
    return InstrumentMetadata(
        symbol="ETH/USDT:USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("1"),
        contract_type="linear",
        is_live=True,
    )


def make_intent(reduce_only=False):
    return OrderIntent(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("2500"),
        size=Decimal("0.01"),
        leverage=Decimal("2"),
        reduce_only=reduce_only,
    )


def test_projected_exposure_includes_position_and_open_orders():
    risk = RiskManager()
    risk.initialize_balance(1000.0)
    adapter = RiskPreFlightAdapter(risk)

    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("2"),
        current_position_size=Decimal("0.08"),
        open_order_exposure=Decimal("0.02"),
    )

    assert adapter.validate_position_limits(account, make_intent(), make_metadata()) is False


def test_reduce_only_order_does_not_add_proposed_exposure():
    risk = RiskManager()
    risk.initialize_balance(1000.0)
    adapter = RiskPreFlightAdapter(risk)

    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("2"),
        current_position_size=Decimal("0.10"),
        open_order_exposure=Decimal("0"),
    )

    assert adapter.validate_position_limits(account, make_intent(reduce_only=True), make_metadata()) is True
