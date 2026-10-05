import copy

import pytest

from engine.risk_manager import RiskManager, RiskRegime


def test_risk_state_round_trips_across_restart():
    original = RiskManager()
    original.initialize_balance(1000.0)
    original.peak_balance = 1250.0
    original.daily_starting_balance = 1000.0
    original.safe_haven = 50.0
    original.kill_switch_triggered = True
    original.current_regime = RiskRegime.PRESERVATION

    envelope = original.export_state()

    restored = RiskManager()
    restored.restore_state(envelope, current_balance=1100.0)

    assert restored.initial_balance == 1000.0
    assert restored.peak_balance == 1250.0
    assert restored.daily_starting_balance == 1000.0
    assert restored.safe_haven == 50.0
    assert restored.kill_switch_triggered is True
    assert restored.current_regime is RiskRegime.PRESERVATION


def test_corrupt_risk_state_fails_closed():
    risk = RiskManager()
    risk.initialize_balance(1000.0)
    envelope = risk.export_state()
    corrupt = copy.deepcopy(envelope)
    corrupt["state"]["peak_balance"] = 1.0

    with pytest.raises(ValueError, match="checksum"):
        risk.restore_state(corrupt, current_balance=1000.0)

    assert risk.trading_halted is True


def test_risk_state_has_version_and_checksum():
    risk = RiskManager()
    risk.initialize_balance(1000.0)
    envelope = risk.export_state()

    assert envelope["version"] == 1
    assert len(envelope["checksum"]) == 64
