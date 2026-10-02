import logging
from decimal import Decimal
from preflight_layer.interfaces import IExchangeAdapter
from preflight_layer.domain import InstrumentMetadata, AccountState, MarketData
from engine.exchange import OKXEngine
from adapters.market_stream import OKXMarketStream

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
        # OKXEngine.initialize() içinde load_markets() çağrıldığı için veriler önbellektedir
        market = self.okx.exchange.market(instrument_id)
        
        # 'info' anahtarı OKX'in bize döndüğü orijinal ham JSON verisini tutar
        raw_info = market.get('info', {})

        return InstrumentMetadata(
            symbol=instrument_id,
            min_size=Decimal(str(raw_info.get("minSz", market["limits"]["amount"]["min"]))),
            tick_size=Decimal(str(raw_info.get("tickSz", market["precision"]["price"]))),
            lot_size=Decimal(str(raw_info.get("lotSz", market["precision"]["amount"]))),
            contract_val=Decimal(str(raw_info.get("ctVal", "1"))),
            is_live=raw_info.get("state", "live") == "live",
        )

    async def fetch_account_state(self) -> AccountState:
        """
        Hesabın anlık bakiye ve marjin durumunu çeker.
        """
        # OKXEngine'deki fetch_balance sadece 'total' dönüyor. 
        # Risk motorunun doğru karar vermesi için 'free' ve 'used' detaylarına ihtiyacımız var.
        # Bu yüzden doğrudan okx.exchange objesine inerek tam veriyi çekiyoruz.
        balance_data = await self.okx.exchange.fetch_balance()
        usdt_bal = balance_data.get('USDT', {})

        return AccountState(
            balance=Decimal(str(usdt_bal.get("total", 0.0))),
            available_margin=Decimal(str(usdt_bal.get("free", 0.0))),
            leverage=Decimal(str(config.LEVERAGE)),
        )

    async def fetch_market_data(self, instrument_id: str) -> MarketData:
        """
        Enstrümanın anlık tahta, gösterge (mark) ve endeks fiyatlarını çeker.
        """
        ticker = await self.okx.exchange.fetch_ticker(instrument_id)
        raw_info = ticker.get('info', {})

        return MarketData(
            bid=Decimal(str(ticker.get("bid") or ticker["last"])),
            ask=Decimal(str(ticker.get("ask") or ticker["last"])),
            last=Decimal(str(ticker["last"])),
            timestamp=float(ticker.get("timestamp") or 0) / 1000,
        )