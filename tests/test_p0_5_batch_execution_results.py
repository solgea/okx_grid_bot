from types import SimpleNamespace

import pytest

from engine.sync_engine import ExecutionStatus, OrderSyncEngine


@pytest.mark.asyncio
async def test_batch_results_classify_success_and_rejection():
    engine = SimpleNamespace(
        create_orders=__import__("unittest").mock.AsyncMock(
            return_value=[
                {"id": "ord-1", "status": "open"},
                {"info": {"sCode": "51008", "sMsg": "Insufficient margin"}},
            ]
        )
    )
    sync = OrderSyncEngine(engine)
    specs = [
        SimpleNamespace(side="buy", size=1, price=100, pos_side="net", cl_ord_id="a"),
        SimpleNamespace(side="buy", size=1, price=101, pos_side="net", cl_ord_id="b"),
    ]

    report = await sync._place_batch(specs)

    assert report.statuses == (ExecutionStatus.SUCCESS, ExecutionStatus.REJECTED)


@pytest.mark.asyncio
async def test_batch_unknown_result_fails_closed():
    engine = SimpleNamespace(
        create_orders=__import__("unittest").mock.AsyncMock(
            return_value=[{"status": "open"}]
        )
    )
    sync = OrderSyncEngine(engine)
    specs = [
        SimpleNamespace(side="buy", size=1, price=100, pos_side="net", cl_ord_id="a"),
        SimpleNamespace(side="buy", size=1, price=101, pos_side="net", cl_ord_id="b"),
    ]

    with pytest.raises(RuntimeError, match="UNKNOWN"):
        await sync._place_batch(specs)


@pytest.mark.asyncio
async def test_batch_transport_failure_is_not_reclassified_as_rejection():
    error = RuntimeError("timeout")
    engine = SimpleNamespace(
        create_orders=__import__("unittest").mock.AsyncMock(side_effect=error)
    )
    sync = OrderSyncEngine(engine)
    specs = [
        SimpleNamespace(side="buy", size=1, price=100, pos_side="net", cl_ord_id="a")
    ]

    with pytest.raises(RuntimeError, match="timeout"):
        await sync._place_batch(specs)
