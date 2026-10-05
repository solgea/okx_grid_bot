import logging
import time
from decimal import Decimal, InvalidOperation

from config.settings import config
from preflight_layer.risk_policy import RiskPolicy
from preflight_layer.domain import (
    OrderIntent, InstrumentMetadata, AccountState, MarketData,
    PreFlightState, ValidationResult, ValidationCheck,
    PF001_INVALID_INSTRUMENT, PF002_INSTRUMENT_NOT_LIVE, PF004_INVALID_TICK_SIZE, PF005_INVALID_LOT_SIZE, PF013_INVALID_CONTRACT_VALUE,
    PF006_INVALID_MIN_SIZE, PF007_INVALID_PRICE, PF008_PRICE_TICK_MISMATCH,
    PF009_INVALID_QUANTITY, PF010_QUANTITY_BELOW_MIN, PF011_QUANTITY_LOT_MISMATCH,
    PF015_INVALID_LEVERAGE, PF016_LEVERAGE_EXCEEDED, PF017_INSUFFICIENT_MARGIN,
    PF018_MAX_SIZE_EXCEEDED, PF025_STALE_MARKET_DATA, PF026_MARKET_DATA_UNAVAILABLE, PF027_ACCOUNT_CONFIGURATION_INVALID, PF029_KILL_SWITCH, PF030_TRADING_HALTED,
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
    def __init__(self, risk_manager=None, policy: RiskPolicy | None = None):
        self.risk_manager = risk_manager
        self.policy = policy or RiskPolicy.from_config()
        self.state = PreFlightState.CREATED

    @staticmethod
    def _contract_notional(intent: OrderIntent, metadata: InstrumentMetadata) -> Decimal:
        """Return quote-currency notional for linear/inverse OKX contracts."""
        contracts = intent.size
        price = intent.price
        ct_val = metadata.contract_val
        if contracts <= 0 or price <= 0 or ct_val <= 0:
            raise ValueError("Invalid contract sizing inputs")
        contract_type = metadata.contract_type.lower()
        if contract_type == "linear":
            return contracts * ct_val * price
        if contract_type == "inverse":
            return contracts * ct_val / price
        raise ValueError(f"Unsupported contract type: {metadata.contract_type}")

    @staticmethod
    def _reject(result, code, message):
        result.passed = False
        result.rejection_code = code
        result.message = message
        result.checks.append(ValidationCheck("preflight", False, message))
        return PreFlightState.REJECTED

    def validate(self, intent, metadata, account, market):
        result = ValidationResult(passed=True)
        self.state = PreFlightState.CREATED

        if config.KILL_SWITCH_ACTIVE:
            self.state = self._reject(result, PF029_KILL_SWITCH, "Trading blocked by active kill switch.")
            return result

        if self.risk_manager and getattr(self.risk_manager, "is_trading_halted", lambda: False)():
            self.state = self._reject(result, PF030_TRADING_HALTED, "Trading is halted.")
            return result

        if metadata is None:
            self.state = self._reject(result, PF026_MARKET_DATA_UNAVAILABLE, "Instrument metadata unavailable.")
            return result
        if intent.instrument_id != metadata.symbol:
            self.state = self._reject(
                result,
                PF001_INVALID_INSTRUMENT,
                f"Instrument {intent.instrument_id} does not match metadata symbol {metadata.symbol}.",
            )
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
        if metadata.contract_val <= 0:
            self.state = self._reject(result, PF013_INVALID_CONTRACT_VALUE, "Invalid exchange contract value.")
            return result
        if metadata.contract_type.lower() not in {"linear", "inverse"}:
            self.state = self._reject(result, PF014_INVALID_CONTRACT_TYPE, f"Unsupported contract type: {metadata.contract_type}.")
            return result
        if intent.price is None or intent.price <= 0:
            self.state = self._reject(result, PF007_INVALID_PRICE, "Order price must be positive.")
            return result
        if intent.size <= 0:
            self.state = self._reject(result, PF009_INVALID_QUANTITY, "Order size must be positive.")
            return result
        if intent.size < metadata.min_size:
            self.state = self._reject(result, PF010_QUANTITY_BELOW_MIN, f"Order size {intent.size} is below minimum {metadata.min_size}.")
            return result
        max_size = Decimal(str(self.policy.max_position_size))
        if intent.size > max_size:
            self.state = self._reject(result, PF018_MAX_SIZE_EXCEEDED, f"Order size {intent.size} exceeds maximum {max_size}.")
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
        if account is None or account.leverage <= 0:
            self.state = self._reject(result, PF027_ACCOUNT_CONFIGURATION_INVALID, "Invalid account leverage configuration.")
            return result
        if account.available_margin <= 0:
            self.state = self._reject(result, PF017_INSUFFICIENT_MARGIN, "No available margin.")
            return result
        if intent.leverage > account.leverage or intent.leverage > Decimal(str(self.policy.max_leverage)):
            self.state = self._reject(result, PF016_LEVERAGE_EXCEEDED, f"Intent leverage {intent.leverage} exceeds account leverage {account.leverage}.")
            return result

        self.state = PreFlightState.METADATA_VALIDATED

        if market is None or market.last <= 0:
            self.state = self._reject(result, PF026_MARKET_DATA_UNAVAILABLE, "Market data unavailable.")
            return result
        age = time.time() - market.timestamp
        if age < 0 or age > self.policy.market_data_max_age_sec:
            self.state = self._reject(result, PF025_STALE_MARKET_DATA, f"Market data is stale ({age:.1f}s).")
            return result

        try:
            estimated_notional = self._contract_notional(intent, metadata)
        except ValueError as exc:
            self.state = self._reject(result, PF013_INVALID_CONTRACT_VALUE, str(exc))
            return result
        required_margin = estimated_notional / intent.leverage
        if required_margin > account.available_margin:
            self.state = self._reject(result, PF017_INSUFFICIENT_MARGIN, f"Required margin {required_margin} exceeds available margin {account.available_margin}.")
            return result

        if self.risk_manager and not self.risk_manager.validate_risk(account, intent, metadata):
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
            if result.passed:
                accepted.append(intent)
            else:
                rejected.append((intent, result))
        if rejected:
            logger.warning("Batch preflight rejected %s/%s orders", len(rejected), len(intents))
        return accepted, rejected
