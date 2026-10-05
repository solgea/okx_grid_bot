from config.settings import config
from engine.risk_manager import RiskManager
from preflight_layer.risk_policy import RiskPolicy
from preflight_layer.validator import PreFlightValidator


def test_risk_policy_is_single_config_projection():
    policy = RiskPolicy.from_config()

    assert policy.max_position_size == float(config.MAX_POSITION_SIZE)
    assert policy.max_drawdown_pct == float(config.MAX_DRAWDOWN_PCT)
    assert policy.max_daily_loss_usdt == float(config.MAX_DAILY_LOSS_USDT)
    assert policy.market_data_max_age_sec == float(config.MARKET_DATA_MAX_AGE_SEC)
    assert policy.max_leverage == float(config.LEVERAGE)


def test_risk_components_share_same_policy_instance():
    policy = RiskPolicy.from_config()
    risk = RiskManager(policy=policy)

    from adapters.risk_adapter import RiskPreFlightAdapter

    adapter = RiskPreFlightAdapter(risk, policy=policy)
    validator = PreFlightValidator(risk_manager=adapter, policy=policy)

    assert risk.policy is policy
    assert adapter.policy is policy
    assert validator.policy is policy


def test_validator_uses_policy_max_leverage():
    from decimal import Decimal
    from preflight_layer.domain import AccountState, InstrumentMetadata, MarketData, OrderIntent, OrderSide, OrderType

    policy = RiskPolicy(
        max_position_size=0.1,
        max_drawdown_pct=20.0,
        max_daily_loss_usdt=500.0,
        market_data_max_age_sec=30.0,
        max_leverage=2.0,
    )
    validator = PreFlightValidator(policy=policy)
    intent = OrderIntent(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("2500"),
        size=Decimal("0.01"),
        leverage=Decimal("3"),
    )
    metadata = InstrumentMetadata(
        symbol="ETH/USDT:USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("1"),
        is_live=True,
    )
    account = AccountState(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("10"),
    )
    import time
    market = MarketData(last=Decimal("2500"), timestamp=time.time())

    result = validator.validate(intent, metadata, account, market)

    assert result.passed is False
