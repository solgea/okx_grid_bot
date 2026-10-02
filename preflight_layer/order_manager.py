import logging
from preflight_layer.domain import OrderIntent, PreFlightState

# IExchangeAdapter eğer interfaces içinde yoksa duck-typing ile geçilebilir, 
# varsa bu satırı aktif bırakabilirsin.
# from preflight_layer.interfaces import IExchangeAdapter 

from preflight_layer.validator import PreFlightValidator

logger = logging.getLogger("OrderManager")

class OrderManager:
    def __init__(self, adapter, validator: PreFlightValidator):
        self.adapter = adapter
        self.validator = validator

    def validate_intents(self, intents, metadata, account, market):
        """Validate a batch against one exchange snapshot before synchronization."""
        accepted, rejected = self.validator.validate_batch(
            intents, metadata, account, market
        )
        for intent, result in rejected:
            logger.warning(
                "PreFlight emri filtreledi: instrument=%s code=%s",
                intent.instrument_id,
                result.rejection_code,
            )
        return accepted

    async def execute_intent(self, intent: OrderIntent) -> bool:
        logger.info(f"Received OrderIntent for {intent.instrument_id}")
        
        # Borsa ve hesap verilerini topla
        metadata = await self.adapter.fetch_instrument_metadata(intent.instrument_id)
        account = await self.adapter.fetch_account_state()
        market = await self.adapter.fetch_market_data(intent.instrument_id)
        
        # PreFlight (Uçuş Öncesi) Doğrulama Boru Hattı
        result = self.validator.validate(intent, metadata, account, market)
        
        if not result.passed or self.validator.state != PreFlightState.AUTHORIZED:
            logger.error(f"Order intent rejected by PreFlight: {result.rejection_code} - {result.message}")
            return False
            
        logger.info(f"PreFlight PASSED. Executing order for {intent.instrument_id}.")
        # Burada adapter üzerinden işlem borsaya iletilecek. Örn:
        # await self.adapter.place_order(intent)
        return True