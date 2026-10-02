import pytest

from adapters.market_stream import MarketEventPool, OKXMarketStream
from preflight_layer.cache import load_state, save_state
from strategy.grid_engine import GridEngine, GridState


def test_market_event_pool_reuses_event_objects():
    pool = MarketEventPool(size=1)
    first = pool.acquire()
    first.price = 123.4
    pool.release(first)
    second = pool.acquire()

    assert second is first
    assert second.price == 0.0


def test_okx_candle_event_decoding():
    stream = OKXMarketStream("ETH-USDT-SWAP", "1m")
    event = stream._decode(
        "candle1m",
        ["1700000000000", "100", "105", "99", "103", "42", "1"],
    )

    assert event.ohlcv == (1700000000000, 100.0, 105.0, 99.0, 103.0, 42.0)
    assert event.confirmed is True
    stream.pool.release(event)


@pytest.mark.asyncio
async def test_grid_state_cache_round_trip(tmp_path):
    path = str(tmp_path / "bot_state.json")
    original = GridEngine(100, 200, 5, 0.1)
    original.update_state(150, 0.1, 140)
    await save_state(path, {"grid": original.to_state(), "smc_data": {"mss": "bullish"}})

    restored = GridEngine(1, 2, 2, 0.1)
    state = await load_state(path)
    restored.restore_state(state["grid"])

    assert restored.state == GridState.DISTRIBUTING
    assert restored.lower_price == original.lower_price
    assert restored.grid_levels == original.grid_levels
