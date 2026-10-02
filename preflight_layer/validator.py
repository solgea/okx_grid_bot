import logging
from decimal import Decimal, InvalidOperation
import time

from preflight_layer.domain import (
    OrderIntent,
    InstrumentMetadata,
    AccountState,
    MarketData,
    PreFlightState,
    ValidationResult,
    ValidationCheck,
    PF002_INSTRUMENT_NOT_LIVE,
    PF004_INVALID_TICK_SIZE,
    PF005_INVALID_LOT_SIZE,
    PF006_INVALID_MIN_SIZE,
    PF007_INVALID_PRICE,
    PF008_PRICE_TICK_MISMATCH,
    PF009_INVALID_QUANTITY,
    PF011_QUANTITY_LOT_MISMATCH,
    PF015_INVALID_LEVERAGE,
    PF016_LEVERAGE_EXCEEDED,
    PF017_INSUFFICIENT_MARGIN,
    PF018_MAX_SIZE_EXCEEDED,
    PF025_STALE_MARKET_DATA,
    PF026_MARKET_DATA_UNAVAILABLE,
)


logger = logging.getLogger("PreFlightValidator")


def _aligned(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return False
    try:
        return (value / step).to_integral_value() == value / step
    except (InvalidOperation, ZeroDivisionError):
        return False


class PreFlightValidator:
    def __init__(self, risk_manager=None):
        self.risk_manager = risk_manager
        self.state = PreFlightState.CREATED

    @staticmethod
    def _reject(result, code, message, state=PreFlightState.REJECTED):
        result.passed = False
        result.rejection_code = code
        result.message = message
        result.checks.append(ValidationCheck("preflight", False, message))
        return state

    def validate(self, intent, metadata, account, market):
        result = ValidationResult(passed=True)
        self.state = PreFlightState.CREATED

        if metadata is None:
            self.state = self._reject(result, PF026_MARKET_DATA_UNAVAILABLE, "Instrument metadata unavailable.")
            return result
        if not metadata.is_live:
            self.state = self._reject(result, PF002_INSTRUMENT_NOT_LIVE, "Instrument is not live.")
            return result
        if metadata.tick_size <= 0:
            self.state = self._reject(result, PF004_INVALID_TICK_SIZE, "Invalid exchange tick size.")
            return result
        if metadata.lot_size <= 0:
            self.state = self._reject(result, PF005_INVALID_LOT_SIZE, "Invalid exchange lot size.")
            return result
        if metadata.min_size <= 0:
            self.state = self._reject(result, PF006_INVALID_MIN_SIZE, "Invalid exchange minimum size.")
            return result
        if intent.price is None or intent.price <= 0:
            self.state = self._reject(result, PF007_INVALID_PRICE, "Order price must be positive.")
            return result
        if intent.size <= 0:
            self.state = self._reject(result, PF009_INVALID_QUANTITY, "Order size must be positive.")
            return result
        if intent.size < metadata.min_size:
            self.state = self._reject(result, "PF010_QUANTITY_BELOW_MIN", f"Order size {intent.size} is below minimum {metadata.min_size}.")
            return result
        if not _aligned(intent.price, metadata.tick_size):
            self.state = self._reject(result, PF008_PRICE_TICK_MISMATCH, f"Price {intent.price} is not aligned to tick size {metadata.tick_size}.")
            return result
        if not _aligned(intent.size, metadata.lot_size):
            self.state = self._reject(result, PF011_QUANTITY_LOT_MISMATCH, f"Size {intent.size} is not aligned to lot size {metadata.lot_size}.")
            return result
        if intent.leverage <= 0:
            self.state = self._reject(result, PF015_INVALID_LEVERAGE, "Leverage must be positive.")
            return result
        if intent.leverage > Decimal(str(account.leverage)):
            self.state = self._reject(result, PF016_LEVERAGE_EXCEEDED, f"Intent leverage {intent.leverage} exceeds account leverage {account.leverage}.")
            return result

        self.state = PreFlightState.METADATA_VALIDATED

        if market is None or market.last <= 0:
            self.state = self._reject(result, PF026_MARKET_DATA_UNAVAILABLE, "Market data unavailable.")
            return result
        age = time.time() - market.timestamp
        if age > getattr(__import__("config.settings", fromlist=["config"]).config, "MARKET_DATA_MAX_AGE_SEC", 30.0):
            self.state = self._reject(result, PF025_STALE_MARKET_DATA, f"Market data is stale ({age:.1f}s).")
            return result

        estimated_cost = intent.size * intent.price
        if account.available_margin <= 0 or estimated_cost > account.available_margin * max(intent.leverage, Decimal("1")):
            self.state = self._reject(result, PF017_INSUFFICIENT_MARGIN, "Insufficient available margin for order.")
            return result

        if intent.size > metadata.min_size and hasattr(metadata, "max_size"):
            if intent.size > metadata.max_size:
                self.state = self._reject(result, PF018_MAX_SIZE_EXCEEDED, "Order size exceeds exchange maximum.")
                return result

        if self.risk_manager and not self.risk_manager.validate_risk(account, intent):
            self.state = self._reject(result, "RISK_VALIDATION_FAILED", "Order rejected by risk manager.")
            logger.warning("PreFlight risk rejection: instrument=%s size=%s", intent.instrument_id, intent.size)
            return result

        self.state = PreFlightState.RISK_CHECKED
        self.state = PreFlightState.AUTHORIZED
        return result

    def validate_batch(self, intents, metadata, account, market):
        accepted, rejected = [], []
        for intent in intents:
            result = self.validate(intent, metadata, account, market)
            (accepted if result.passed else rejected).append(intent if result.passed else (intent, result))
        if rejected:
            logger.warning("Batch preflight rejected %s/%s orders", len(rejected), len(intents))
        return accepted, rejected
