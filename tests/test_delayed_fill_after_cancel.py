from decimal import Decimal

import pytest

from demo_exec.lifecycle import Lifecycle, LifecycleState
from demo_exec.order_events import OrderEvent, OrderEventProcessor


def _cancel_confirmed_processor() -> OrderEventProcessor:
    lifecycle = Lifecycle()
    for state in (
        LifecycleState.SUBMITTED,
        LifecycleState.ACKED,
        LifecycleState.OPEN,
        LifecycleState.CANCEL_SENT,
        LifecycleState.CANCEL_CONFIRMED,
    ):
        lifecycle.transition(state)
    return OrderEventProcessor(order_quantity=Decimal("10"), lifecycle=lifecycle)


@pytest.mark.parametrize(
    ("late_state", "filled", "expected"),
    [
        (LifecycleState.PARTIAL, Decimal("2"), LifecycleState.PARTIAL),
        (LifecycleState.FILLED, Decimal("10"), LifecycleState.FILLED),
    ],
)
def test_t09_handler_applies_delayed_fill_after_cancel_confirmation(
    late_state, filled, expected
):
    """Exercise the order-event handler, not only direct lifecycle transitions."""
    processor = _cancel_confirmed_processor()

    assert processor.process(OrderEvent("evt-late", late_state, filled)) is True
    assert processor.lifecycle.state is expected
    assert processor.cumulative_filled == filled


def test_t09_handler_uses_cumulative_quantity_and_ignores_duplicate_event():
    processor = _cancel_confirmed_processor()
    partial = OrderEvent("evt-1", LifecycleState.PARTIAL, Decimal("2"))

    assert processor.process(partial) is True
    assert processor.process(partial) is False
    assert processor.cumulative_filled == Decimal("2")
    assert processor.lifecycle.state is LifecycleState.PARTIAL


def test_t09_handler_ignores_stale_lower_cumulative_fill_without_regression():
    processor = _cancel_confirmed_processor()
    assert processor.process(
        OrderEvent("evt-newer", LifecycleState.PARTIAL, Decimal("4"))
    ) is True

    assert processor.process(
        OrderEvent("evt-older", LifecycleState.PARTIAL, Decimal("2"))
    ) is False
    assert processor.cumulative_filled == Decimal("4")
    assert processor.lifecycle.state is LifecycleState.PARTIAL


def test_t09_handler_does_not_regress_filled_state_on_late_partial():
    processor = _cancel_confirmed_processor()
    assert processor.process(
        OrderEvent("evt-filled", LifecycleState.FILLED, Decimal("10"))
    ) is True

    assert processor.process(
        OrderEvent("evt-delayed-partial", LifecycleState.PARTIAL, Decimal("7"))
    ) is False
    assert processor.lifecycle.state is LifecycleState.FILLED
    assert processor.cumulative_filled == Decimal("10")


def test_t09_handler_rejects_filled_event_with_incomplete_quantity():
    processor = _cancel_confirmed_processor()
    with pytest.raises(ValueError, match="FILLED requires"):
        processor.process(
            OrderEvent("evt-invalid", LifecycleState.FILLED, Decimal("9"))
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("late_state", "filled", "expected"),
    [
        (LifecycleState.PARTIAL, Decimal("0.25"), LifecycleState.PARTIAL),
        (LifecycleState.FILLED, Decimal("1"), LifecycleState.FILLED),
    ],
)
async def test_t09_executor_event_ingress_handles_fill_after_cancel_confirmation(
    late_state, filled, expected
):
    """Exercise the executor routing method, without any exchange transport."""
    from demo_exec.executor import DemoExecutor
    from demo_exec.intent import Intent
    from demo_exec.transport import NullTransport

    executor = DemoExecutor(NullTransport())
    result = await executor.submit(
        Intent.create("agent1", "ETH/USDT:USDT", "buy", "offline late-fill", 101)
    )
    assert result.accepted is True
    cl_id = result.client_order_id

    assert executor.handle_order_event(
        cl_id, OrderEvent("evt-ack", LifecycleState.ACKED, Decimal("0"))
    ) is True
    assert executor.handle_order_event(
        cl_id, OrderEvent("evt-open", LifecycleState.OPEN, Decimal("0"))
    ) is True
    executor.mark_cancel_sent(cl_id)
    assert executor.handle_order_event(
        cl_id, OrderEvent("evt-cancel-confirmed", LifecycleState.CANCEL_CONFIRMED, Decimal("0"))
    ) is True

    late = OrderEvent("evt-late-fill", late_state, filled)
    assert executor.handle_order_event(cl_id, late) is True
    assert executor.handle_order_event(cl_id, late) is False
    processor = executor._order_events[cl_id]
    assert processor.lifecycle.state is expected
    assert processor.cumulative_filled == filled


@pytest.mark.asyncio
async def test_t09_executor_stops_on_unknown_order_event_identity():
    from demo_exec.executor import DemoExecutor
    from demo_exec.intent import Intent
    from demo_exec.transport import NullTransport

    executor = DemoExecutor(NullTransport())
    with pytest.raises(ValueError, match="E_UNKNOWN_CLIENT_ORDER_ID"):
        executor.handle_order_event(
            "unknown-order",
            OrderEvent("evt-unknown", LifecycleState.FILLED, Decimal("1")),
        )

    result = await executor.submit(
        Intent.create("agent1", "ETH/USDT:USDT", "buy", "must stay stopped", 102)
    )
    assert result.accepted is False
    assert result.code == "E_AGENT_STATE"
