import pytest

from demo_exec.protection_deadline import (
    PROTECT_DEADLINE_SEC,
    ProtectionDeadline,
    ProtectionStatus,
)


def test_t17_deadline_starts_at_first_position_detection():
    guard = ProtectionDeadline()
    assert guard.status is ProtectionStatus.WAITING_FOR_POSITION
    assert guard.position_detected(100.0) is True
    assert guard.status is ProtectionStatus.UNPROTECTED
    assert guard.check(100.0 + PROTECT_DEADLINE_SEC) is ProtectionStatus.UNPROTECTED
    assert guard.confirm_protection(100.0 + PROTECT_DEADLINE_SEC) is True
    assert guard.status is ProtectionStatus.PROTECTED
    assert guard.emergency_action_required is False


def test_t17_delayed_protection_after_deadline_requires_emergency_action():
    guard = ProtectionDeadline()
    guard.position_detected(20.0)

    assert guard.check(20.0 + PROTECT_DEADLINE_SEC + 0.001) is ProtectionStatus.EXPIRED
    assert guard.emergency_action_required is True
    # Late confirmation must not clear the fail-closed state.
    assert guard.confirm_protection(26.0) is False
    assert guard.status is ProtectionStatus.EXPIRED


def test_t17_duplicate_position_detection_cannot_reset_deadline():
    guard = ProtectionDeadline()
    assert guard.position_detected(10.0) is True
    assert guard.position_detected(14.9) is False

    assert guard.check(15.001) is ProtectionStatus.EXPIRED
    assert guard.emergency_action_required is True


def test_t17_check_before_position_detection_does_not_start_clock():
    guard = ProtectionDeadline()
    assert guard.check(500.0) is ProtectionStatus.WAITING_FOR_POSITION
    assert guard.detected_at is None


def test_t17_missing_detection_cannot_be_marked_protected():
    guard = ProtectionDeadline()
    assert guard.confirm_protection(1.0) is False
    assert guard.status is ProtectionStatus.EXPIRED
    assert guard.emergency_action_required is True


@pytest.mark.parametrize("bad_time", [float("nan"), float("inf"), float("-inf")])
def test_t17_non_finite_timestamps_are_rejected(bad_time):
    guard = ProtectionDeadline()
    with pytest.raises(ValueError, match="finite"):
        guard.position_detected(bad_time)


def test_t17_invalid_deadline_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        ProtectionDeadline(deadline_sec=0)
