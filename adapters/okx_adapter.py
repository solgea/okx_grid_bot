import logging
from decimal import Decimal
from preflight_layer.interfaces import IExchangeAdapter
from preflight_layer.domain import InstrumentMetadata, AccountState, MarketData
from preflight_layer.exchange_data import (
    account_state_from_balance,
    instrument_metadata_from_market,
    market_data_from_ticker,
)
from engine.exchange import OKXEngine
from adapters.market_stream import OKXMarketStream
from config.settings import config

logger = logging.getLogger("OKXPreFlightAdapter")

class OKXPreFlightAdapter(IExchangeAdapter):
    def __init__(self, okx_engine: OKXEngine):
        """Mevcut OKXEngine örneğini (instance) adaptöre enjekte ediyoruz."""
        self.okx = okx_engine
        self.market_stream = None

    def market_events(self, instrument_id: str, timeframe: str):
        """Return the native event-driven public market stream."""
        self.market_stream = OKXMarketStream(instrument_id, timeframe)
        return self.market_stream.events()

    async def create_orders(self, instrument_id: str, orders):
        """Delegate an already preflight-approved batch to the exchange engine."""
        return await self.okx.create_orders(instrument_id, orders)

    async def cancel_orders(self, instrument_id: str, order_ids):
        """Delegate cancellation deltas as one batch."""
        return await self.okx.cancel_orders(order_ids, instrument_id)

    async def fetch_instrument_metadata(self, instrument_id: str) -> InstrumentMetadata:
        """
        CCXT üzerinden yüklenen market verisinden OKX'in ham (raw) swap
        bilgilerini alarak Domain modeline dönüştürür.
        """
        market = self.okx.exchange.market(instrument_id)
        return instrument_metadata_from_market(instrument_id, market)

    async def fetch_account_state(self) -> AccountState:
        """
        Hesabın anlık bakiye ve marjin durumunu çeker.
        """
        balance_data = await self.okx.exchange.fetch_balance()
        return account_state_from_balance(
            balance_data, Decimal(str(config.LEVERAGE))
        )

    async def fetch_market_data(self, instrument_id: str) -> MarketData:
        """
        Enstrümanın anlık tahta, gösterge (mark) ve endeks fiyatlarını çeker.
        """
        ticker = await self.okx.exchange.fetch_ticker(instrument_id)
        return market_data_from_ticker(ticker)
