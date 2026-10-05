from config.settings import config
from main import emergency_flatten_authorized


def test_emergency_flatten_is_off_by_default(monkeypatch):
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_ENABLED", False)
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", False)

    assert emergency_flatten_authorized(1.0) is False


def test_emergency_flatten_requires_both_gates(monkeypatch):
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_ENABLED", True)
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", False)

    assert emergency_flatten_authorized(1.0) is False

    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", True)
    assert emergency_flatten_authorized(1.0) is True


def test_no_position_never_flattens(monkeypatch):
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_ENABLED", True)
    monkeypatch.setattr(config, "EMERGENCY_FLATTEN_AUTHORIZED", True)

    assert emergency_flatten_authorized(0.0) is False
