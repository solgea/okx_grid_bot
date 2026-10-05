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
