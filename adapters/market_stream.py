import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator

import websockets

logger = logging.getLogger("OKXMarketStream")


@dataclass(slots=True)
class MarketEvent:
    channel: str = ""
    instrument_id: str = ""
    price: float = 0.0
    timestamp: int = 0
    confirmed: bool = False
    ohlcv: tuple[float, float, float, float, float, int] | None = None


class MarketEventPool:
    def __init__(self, size: int = 256):
        self._available = [MarketEvent() for _ in range(size)]

    def acquire(self) -> MarketEvent:
        return self._available.pop() if self._available else MarketEvent()

    def release(self, event: MarketEvent) -> None:
        event.channel = ""
        event.instrument_id = ""
        event.price = 0.0
        event.timestamp = 0
        event.confirmed = False
        event.ohlcv = None
        self._available.append(event)


class OKXMarketStream:
    URL = "wss://ws.okx.com:8443/ws/v5/public"

    def __init__(self, instrument_id: str, timeframe: str, pool: MarketEventPool | None = None):
        self.instrument_id = instrument_id
        self.timeframe = timeframe
        self.pool = pool or MarketEventPool()

    async def events(self) -> AsyncIterator[MarketEvent]:
        """Yield pooled ticker/candle events and reconnect on transient disconnects."""
        delay = 1
        while True:
            try:
                async with websockets.connect(self.URL, ping_interval=20, ping_timeout=20) as socket:
                    await socket.send(json.dumps({
                        "op": "subscribe",
                        "args": [
                            {"channel": "tickers", "instId": self.instrument_id},
                            {"channel": f"candle{self.timeframe}", "instId": self.instrument_id},
                        ],
                    }))
                    delay = 1
                    async for message in socket:
                        payload = json.loads(message)
                        if payload.get("event") or not payload.get("data"):
                            continue
                        event = self._decode(payload.get("arg", {}).get("channel", ""), payload["data"][0])
                        if event:
                            yield event
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as error:
                logger.warning("OKX market stream disconnected: %s", error)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    def _decode(self, channel: str, data) -> MarketEvent | None:
        event = self.pool.acquire()
        event.channel = channel
        event.instrument_id = self.instrument_id
        if channel == "tickers":
            event.timestamp = int(data.get("ts", 0))
        else:
            event.timestamp = int(data[0])
        if channel == "tickers":
            event.price = float(data.get("last", 0))
        elif channel.startswith("candle"):
            event.ohlcv = (event.timestamp,) + tuple(
                float(value) for value in data[1:6]
            )
            event.price = event.ohlcv[4]
            event.confirmed = str(data[6]) == "1"
        else:
            self.pool.release(event)
            return None
        return event
