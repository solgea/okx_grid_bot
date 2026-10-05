from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from adapters.okx_adapter import OKXPreFlightAdapter


@pytest.mark.asyncio
async def test_account_adapter_preserves_real_available_margin():
    exchange = Mock()
    exchange.exchange = Mock()
    exchange.exchange.fetch_balance = AsyncMock(
        return_value={"USDT": {"total": 1250.0, "free": 137.5}}
    )
    adapter = OKXPreFlightAdapter(exchange)

    snapshot = await adapter.fetch_account_state()

    assert snapshot.balance == Decimal("1250.0")
    assert snapshot.available_margin == Decimal("137.5")
    assert snapshot.available_margin != snapshot.balance
