import logging
from pydantic import BaseModel
from preflight_layer.domain import (
    OrderIntent, InstrumentMetadata, AccountState, MarketData,
    PreFlightState, ValidationResult, ValidationCheck
)

logger = logging.getLogger("PreFlightValidator")

class PreFlightValidator:
    def __init__(self, risk_manager=None):
        self.risk_manager = risk_manager
        self.state = PreFlightState.CREATED

    def validate(
        self, 
        intent: OrderIntent, 
        metadata: InstrumentMetadata, 
        account: AccountState, 
        market: MarketData
    ) -> ValidationResult:
        
        result = ValidationResult(passed=True)
        self.state = PreFlightState.CREATED
        
        # --- 1. METADATA (BORSA LİMİT) KONTROLLERİ ---
        if metadata and intent.size < metadata.min_size:
            result.passed = False
            result.rejection_code = "MIN_SIZE_VIOLATION"
            result.message = f"Emir lot miktarı ({intent.size}), OKX minimum sınırından ({metadata.min_size}) küçük."
            self.state = PreFlightState.REJECTED
            return result
            
        self.state = PreFlightState.METADATA_VALIDATED
        
        # --- 2. RİSK MOTORU KONTROLLERİ ---
        if self.risk_manager:
            risk_passed = self.risk_manager.validate_risk(account, intent)
            if not risk_passed:
                result.passed = False
                result.rejection_code = "RISK_VALIDATION_FAILED"
                result.message = "Emir risk yöneticisi tarafından reddedildi."
                self.state = PreFlightState.REJECTED
                logger.warning(
                    "PreFlight risk reddi: instrument=%s size=%s",
                    intent.instrument_id,
                    intent.size,
                )
                return result
            self.state = PreFlightState.RISK_CHECKED

        self.state = PreFlightState.AUTHORIZED
        return result

    def validate_batch(self, intents, metadata, account, market):
        """Validate a batch against one consistent exchange snapshot."""
        accepted = []
        rejected = []
        for intent in intents:
            result = self.validate(intent, metadata, account, market)
            if result.passed and self.state == PreFlightState.AUTHORIZED:
                accepted.append(intent)
            else:
                rejected.append((intent, result))
        if rejected:
            logger.warning("Batch preflight rejected %s/%s orders", len(rejected), len(intents))
        return accepted, rejected