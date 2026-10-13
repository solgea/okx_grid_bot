import pytest

from demo_exec.lifecycle import Lifecycle, LifecycleState


@pytest.mark.parametrize(
    ("late_fill", "expected"),
    [
        (LifecycleState.PARTIAL, LifecycleState.PARTIAL),
        (LifecycleState.FILLED, LifecycleState.FILLED),
    ],
)
def test_t09_delayed_fill_after_cancel_confirmation_updates_lifecycle(late_fill, expected):
    """A cancel acknowledgement must not cause a later execution event to be discarded."""
    lifecycle = Lifecycle()
    for state in (
        LifecycleState.SUBMITTED,
        LifecycleState.ACKED,
        LifecycleState.OPEN,
        LifecycleState.CANCEL_SENT,
        LifecycleState.CANCEL_CONFIRMED,
    ):
        lifecycle.transition(state)

    # Simulate a fill notification delivered after cancel confirmation.
    lifecycle.transition(late_fill)

    assert lifecycle.state is expected
