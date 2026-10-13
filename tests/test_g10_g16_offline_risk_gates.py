import pytest

from config.settings import config
from engine.risk_manager import RiskManager
from preflight_layer.risk_policy import RiskPolicy


def make_risk():
    policy = RiskPolicy(
        max_position_size=0.1,
        max_drawdown_pct=3.0,
        max_daily_loss_usdt=20.0,
        market_data_max_age_sec=30.0,
        max_leverage=2.0,
    )
    risk = RiskManager(policy=policy)
    risk.initialize_balance(1000.0)
    return risk


def test_t19_drawdown_threshold_trips_kill_switch(monkeypatch):
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    risk = make_risk()

    assert risk.check_risk_limits(current_balance=970.0, current_position_size=0.0) is True
    assert risk.kill_switch_triggered is True
    assert risk.state_dirty is True


def test_t20_daily_loss_threshold_trips_kill_switch(monkeypatch):
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    risk = make_risk()

    assert risk.check_risk_limits(current_balance=979.0, current_position_size=0.0) is True
    assert risk.kill_switch_triggered is True


def test_t21_position_limit_breach_fails_closed(monkeypatch):
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    risk = make_risk()

    assert risk.check_risk_limits(current_balance=1000.0, current_position_size=0.1001) is True
    assert risk.kill_switch_triggered is False


def test_t22_triggered_kill_switch_is_latched(monkeypatch):
    monkeypatch.setattr(config, "KILL_SWITCH_ACTIVE", True)
    risk = make_risk()
    risk.kill_switch_triggered = True

    assert risk.check_risk_limits(current_balance=1000.0, current_position_size=0.0) is True
