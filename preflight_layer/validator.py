import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from config.settings import config
from preflight_layer.risk_policy import RiskPolicy
from preflight_layer.domain import (
    OrderIntent, InstrumentMetadata,
    PreFlightState, ValidationResult, ValidationCheck,
    PF001_INVALID_INSTRUMENT, PF002_INSTRUMENT_NOT_LIVE, PF004_INVALID_TICK_SIZE, PF005_INVALID_LOT_SIZE, PF013_INVALID_CONTRACT_VALUE,
    PF014_INVALID_CONTRACT_TYPE,
    PF006_INVALID_MIN_SIZE, PF007_INVALID_PRICE, PF008_PRICE_TICK_MISMATCH,
    PF009_INVALID_QUANTITY, PF010_QUANTITY_BELOW_MIN, PF011_QUANTITY_LOT_MISMATCH,
    PF015_INVALID_LEVERAGE, PF016_LEVERAGE_EXCEEDED, PF017_INSUFFICIENT_MARGIN,
    PF018_MAX_SIZE_EXCEEDED, PF025_STALE_MARKET_DATA, PF026_MARKET_DATA_UNAVAILABLE, PF027_ACCOUNT_CONFIGURATION_INVALID, PF029_KILL_SWITCH, PF030_TRADING_HALTED,
)
from preflight_layer.sizing import contract_notional

logger = logging.getLogger("PreFlightValidator")

RISK_VALIDATION_FAILED = "RISK_VALIDATION_FAILED"


def _aligned(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return False
    try:
        return (value / step).to_integral_value() == value / step
    except (InvalidOperation, ZeroDivisionError):
        return False


@dataclass(frozen=True)
class ValidationContext:
    """Everything a rule needs to decide whether an intent is acceptable."""

    intent: OrderIntent
    metadata: Optional[InstrumentMetadata]
    account: object
    market: object
    policy: RiskPolicy
    risk_manager: object


# A rule returns None to pass, or a (rejection_code, message) pair to reject.
Rule = Callable[[ValidationContext], Optional[tuple[str, str]]]


# --- metadata and intent rules -----------------------------------------------
def _reject_kill_switch(ctx: ValidationContext):
    if config.KILL_SWITCH_ACTIVE:
        return PF029_KILL_SWITCH, "Trading blocked by active kill switch."
    return None


def _reject_trading_halted(ctx: ValidationContext):
    risk_manager = ctx.risk_manager
    if risk_manager and getattr(risk_manager, "is_trading_halted", lambda: False)():
        return PF030_TRADING_HALTED, "Trading is halted."
    return None


def _reject_missing_metadata(ctx: ValidationContext):
    if ctx.metadata is None:
        return PF026_MARKET_DATA_UNAVAILABLE, "Instrument metadata unavailable."
    return None


def _reject_instrument_mismatch(ctx: ValidationContext):
    if ctx.intent.instrument_id != ctx.metadata.symbol:
        return PF001_INVALID_INSTRUMENT, (
            f"Instrument {ctx.intent.instrument_id} does not match metadata symbol "
            f"{ctx.metadata.symbol}."
        )
    return None


def _reject_instrument_not_live(ctx: ValidationContext):
    if not ctx.metadata.is_live:
        return PF002_INSTRUMENT_NOT_LIVE, "Instrument is not live."
    return None


def _reject_invalid_tick_size(ctx: ValidationContext):
    if ctx.metadata.tick_size <= 0:
        return PF004_INVALID_TICK_SIZE, "Invalid exchange tick size."
    return None


def _reject_invalid_lot_size(ctx: ValidationContext):
    if ctx.metadata.lot_size <= 0:
        return PF005_INVALID_LOT_SIZE, "Invalid exchange lot size."
    return None


def _reject_invalid_min_size(ctx: ValidationContext):
    if ctx.metadata.min_size <= 0:
        return PF006_INVALID_MIN_SIZE, "Invalid exchange minimum size."
    return None


def _reject_invalid_contract_value(ctx: ValidationContext):
    if ctx.metadata.contract_val <= 0:
        return PF013_INVALID_CONTRACT_VALUE, "Invalid exchange contract value."
    return None


def _reject_invalid_contract_type(ctx: ValidationContext):
    if ctx.metadata.contract_type.lower() not in {"linear", "inverse"}:
        return PF014_INVALID_CONTRACT_TYPE, (
            f"Unsupported contract type: {ctx.metadata.contract_type}."
        )
    return None


def _reject_invalid_price(ctx: ValidationContext):
    if ctx.intent.price is None or ctx.intent.price <= 0:
        return PF007_INVALID_PRICE, "Order price must be positive."
    return None


def _reject_invalid_quantity(ctx: ValidationContext):
    if ctx.intent.size <= 0:
        return PF009_INVALID_QUANTITY, "Order size must be positive."
    return None


def _reject_quantity_below_min(ctx: ValidationContext):
    if ctx.intent.size < ctx.metadata.min_size:
        return PF010_QUANTITY_BELOW_MIN, (
            f"Order size {ctx.intent.size} is below minimum {ctx.metadata.min_size}."
        )
    return None


def _reject_max_size_exceeded(ctx: ValidationContext):
    max_size = Decimal(str(ctx.policy.max_position_size))
    if ctx.intent.size > max_size:
        return PF018_MAX_SIZE_EXCEEDED, (
            f"Order size {ctx.intent.size} exceeds maximum {max_size}."
        )
    return None


def _reject_price_tick_mismatch(ctx: ValidationContext):
    if not _aligned(ctx.intent.price, ctx.metadata.tick_size):
        return PF008_PRICE_TICK_MISMATCH, (
            f"Price {ctx.intent.price} is not aligned to tick size "
            f"{ctx.metadata.tick_size}."
        )
    return None


def _reject_quantity_lot_mismatch(ctx: ValidationContext):
    if not _aligned(ctx.intent.size, ctx.metadata.lot_size):
        return PF011_QUANTITY_LOT_MISMATCH, (
            f"Size {ctx.intent.size} is not aligned to lot size "
            f"{ctx.metadata.lot_size}."
        )
    return None


def _reject_invalid_leverage(ctx: ValidationContext):
    if ctx.intent.leverage <= 0:
        return PF015_INVALID_LEVERAGE, "Leverage must be positive."
    return None


def _reject_invalid_account(ctx: ValidationContext):
    if ctx.account is None or ctx.account.leverage <= 0:
        return PF027_ACCOUNT_CONFIGURATION_INVALID, (
            "Invalid account leverage configuration."
        )
    return None


def _reject_no_available_margin(ctx: ValidationContext):
    if ctx.account.available_margin <= 0:
        return PF017_INSUFFICIENT_MARGIN, "No available margin."
    return None


def _reject_leverage_exceeded(ctx: ValidationContext):
    if (
        ctx.intent.leverage > ctx.account.leverage
        or ctx.intent.leverage > Decimal(str(ctx.policy.max_leverage))
    ):
        return PF016_LEVERAGE_EXCEEDED, (
            f"Intent leverage {ctx.intent.leverage} exceeds account leverage "
            f"{ctx.account.leverage}."
        )
    return None


# --- market, margin and risk rules -------------------------------------------
def _reject_market_unavailable(ctx: ValidationContext):
    if ctx.market is None or ctx.market.last <= 0:
        return PF026_MARKET_DATA_UNAVAILABLE, "Market data unavailable."
    return None


def _reject_stale_market_data(ctx: ValidationContext):
    age = time.time() - ctx.market.timestamp
    if age < 0 or age > ctx.policy.market_data_max_age_sec:
        return PF025_STALE_MARKET_DATA, f"Market data is stale ({age:.1f}s)."
    return None


def _reject_uncalculable_notional(ctx: ValidationContext):
    try:
        contract_notional(ctx.intent, ctx.metadata)
    except ValueError as exc:
        return PF013_INVALID_CONTRACT_VALUE, str(exc)
    return None


def _reject_insufficient_margin(ctx: ValidationContext):
    required_margin = contract_notional(ctx.intent, ctx.metadata) / ctx.intent.leverage
    if required_margin > ctx.account.available_margin:
        return PF017_INSUFFICIENT_MARGIN, (
            f"Required margin {required_margin} exceeds available margin "
            f"{ctx.account.available_margin}."
        )
    return None


def _reject_risk_validation(ctx: ValidationContext):
    risk_manager = ctx.risk_manager
    if risk_manager and not risk_manager.validate_risk(
        ctx.account, ctx.intent, ctx.metadata
    ):
        logger.warning(
            "PreFlight risk rejection: instrument=%s size=%s",
            ctx.intent.instrument_id,
            ctx.intent.size,
        )
        return RISK_VALIDATION_FAILED, "Order rejected by risk manager."
    return None


# Rules are evaluated in order and the first failure rejects the intent.
METADATA_RULES: tuple[Rule, ...] = (
    _reject_kill_switch,
    _reject_trading_halted,
    _reject_missing_metadata,
    _reject_instrument_mismatch,
    _reject_instrument_not_live,
    _reject_invalid_tick_size,
    _reject_invalid_lot_size,
    _reject_invalid_min_size,
    _reject_invalid_contract_value,
    _reject_invalid_contract_type,
    _reject_invalid_price,
    _reject_invalid_quantity,
    _reject_quantity_below_min,
    _reject_max_size_exceeded,
    _reject_price_tick_mismatch,
    _reject_quantity_lot_mismatch,
    _reject_invalid_leverage,
    _reject_invalid_account,
    _reject_no_available_margin,
    _reject_leverage_exceeded,
)

EXECUTION_RULES: tuple[Rule, ...] = (
    _reject_market_unavailable,
    _reject_stale_market_data,
    _reject_uncalculable_notional,
    _reject_insufficient_margin,
    _reject_risk_validation,
)


class PreFlightValidator:
    def __init__(self, risk_manager=None, policy: RiskPolicy | None = None):
        self.risk_manager = risk_manager
        self.policy = policy or RiskPolicy.from_config()
        self.state = PreFlightState.CREATED

    @staticmethod
    def _reject(result, code, message):
        result.passed = False
        result.rejection_code = code
        result.message = message
        result.checks.append(ValidationCheck("preflight", False, message))
        return PreFlightState.REJECTED

    def validate(self, intent, metadata, account, market):
        """Validate one intent against the ordered PreFlight rule set."""
        result = ValidationResult(passed=True)
        self.state = PreFlightState.CREATED

        context = ValidationContext(
            intent=intent,
            metadata=metadata,
            account=account,
            market=market,
            policy=self.policy,
            risk_manager=self.risk_manager,
        )

        for rule in METADATA_RULES:
            rejection = rule(context)
            if rejection is not None:
                code, message = rejection
                self.state = self._reject(result, code, message)
                return result

        self.state = PreFlightState.METADATA_VALIDATED

        for rule in EXECUTION_RULES:
            rejection = rule(context)
            if rejection is not None:
                code, message = rejection
                self.state = self._reject(result, code, message)
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
