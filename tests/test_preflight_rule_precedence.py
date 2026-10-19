"""Differential test: the rule-list validator must behave exactly like the
original sequential-guard implementation.

The original implementation is reproduced verbatim below from git history
(commit 6b4e902) and compared against the new rule-list validator across a
large matrix of inputs.
"""
import itertools
import time
from decimal import Decimal

from config.settings import config
from preflight_layer.domain import (
    AccountState,
    InstrumentMetadata,
    MarketData,
    OrderIntent,
    OrderSide,
    OrderType,
    PreFlightState,
    ValidationCheck,
    ValidationResult,
)
from preflight_layer.risk_policy import RiskPolicy
from preflight_layer.sizing import contract_notional
from preflight_layer.validator import PreFlightValidator

PF = {
    "PF001": "PF001_INVALID_INSTRUMENT",
    "PF002": "PF002_INSTRUMENT_NOT_LIVE",
    "PF004": "PF004_INVALID_TICK_SIZE",
    "PF005": "PF005_INVALID_LOT_SIZE",
    "PF006": "PF006_INVALID_MIN_SIZE",
    "PF007": "PF007_INVALID_PRICE",
    "PF008": "PF008_PRICE_TICK_MISMATCH",
    "PF009": "PF009_INVALID_QUANTITY",
    "PF010": "PF010_QUANTITY_BELOW_MIN",
    "PF011": "PF011_QUANTITY_LOT_MISMATCH",
    "PF013": "PF013_INVALID_CONTRACT_VALUE",
    "PF014": "PF014_INVALID_CONTRACT_TYPE",
    "PF015": "PF015_INVALID_LEVERAGE",
    "PF016": "PF016_LEVERAGE_EXCEEDED",
    "PF017": "PF017_INSUFFICIENT_MARGIN",
    "PF018": "PF018_MAX_SIZE_EXCEEDED",
    "PF025": "PF025_STALE_MARKET_DATA",
    "PF026": "PF026_MARKET_DATA_UNAVAILABLE",
    "PF027": "PF027_ACCOUNT_CONFIGURATION_INVALID",
    "PF029": "PF029_KILL_SWITCH",
    "PF030": "PF030_TRADING_HALTED",
}


def _aligned(value, step):
    if step <= 0:
        return False
    try:
        return (value / step).to_integral_value() == value / step
    except Exception:
        return False


class OriginalValidator:
    """Verbatim copy of the pre-refactor sequential-guard implementation."""

    def __init__(self, risk_manager=None, policy=None):
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
        result = ValidationResult(passed=True)
        self.state = PreFlightState.CREATED

        if config.KILL_SWITCH_ACTIVE:
            self.state = self._reject(result, PF["PF029"], "Trading blocked by active kill switch.")
            return result
        if self.risk_manager and getattr(self.risk_manager, "is_trading_halted", lambda: False)():
            self.state = self._reject(result, PF["PF030"], "Trading is halted.")
            return result
        if metadata is None:
            self.state = self._reject(result, PF["PF026"], "Instrument metadata unavailable.")
            return result
        if intent.instrument_id != metadata.symbol:
            self.state = self._reject(result, PF["PF001"], f"Instrument {intent.instrument_id} does not match metadata symbol {metadata.symbol}.")
            return result
        if not metadata.is_live:
            self.state = self._reject(result, PF["PF002"], "Instrument is not live.")
            return result
        if metadata.tick_size <= 0:
            self.state = self._reject(result, PF["PF004"], "Invalid exchange tick size.")
            return result
        if metadata.lot_size <= 0:
            self.state = self._reject(result, PF["PF005"], "Invalid exchange lot size.")
            return result
        if metadata.min_size <= 0:
            self.state = self._reject(result, PF["PF006"], "Invalid exchange minimum size.")
            return result
        if metadata.contract_val <= 0:
            self.state = self._reject(result, PF["PF013"], "Invalid exchange contract value.")
            return result
        if metadata.contract_type.lower() not in {"linear", "inverse"}:
            self.state = self._reject(result, PF["PF014"], f"Unsupported contract type: {metadata.contract_type}.")
            return result
        if intent.price is None or intent.price <= 0:
            self.state = self._reject(result, PF["PF007"], "Order price must be positive.")
            return result
        if intent.size <= 0:
            self.state = self._reject(result, PF["PF009"], "Order size must be positive.")
            return result
        if intent.size < metadata.min_size:
            self.state = self._reject(result, PF["PF010"], f"Order size {intent.size} is below minimum {metadata.min_size}.")
            return result
        max_size = Decimal(str(self.policy.max_position_size))
        if intent.size > max_size:
            self.state = self._reject(result, PF["PF018"], f"Order size {intent.size} exceeds maximum {max_size}.")
            return result
        if not _aligned(intent.price, metadata.tick_size):
            self.state = self._reject(result, PF["PF008"], f"Price {intent.price} is not aligned to tick size {metadata.tick_size}.")
            return result
        if not _aligned(intent.size, metadata.lot_size):
            self.state = self._reject(result, PF["PF011"], f"Size {intent.size} is not aligned to lot size {metadata.lot_size}.")
            return result
        if intent.leverage <= 0:
            self.state = self._reject(result, PF["PF015"], "Leverage must be positive.")
            return result
        if account is None or account.leverage <= 0:
            self.state = self._reject(result, PF["PF027"], "Invalid account leverage configuration.")
            return result
        if account.available_margin <= 0:
            self.state = self._reject(result, PF["PF017"], "No available margin.")
            return result
        if intent.leverage > account.leverage or intent.leverage > Decimal(str(self.policy.max_leverage)):
            self.state = self._reject(result, PF["PF016"], f"Intent leverage {intent.leverage} exceeds account leverage {account.leverage}.")
            return result

        self.state = PreFlightState.METADATA_VALIDATED

        if market is None or market.last <= 0:
            self.state = self._reject(result, PF["PF026"], "Market data unavailable.")
            return result
        age = time.time() - market.timestamp
        if age < 0 or age > self.policy.market_data_max_age_sec:
            self.state = self._reject(result, PF["PF025"], f"Market data is stale ({age:.1f}s).")
            return result
        try:
            estimated_notional = contract_notional(intent, metadata)
        except ValueError as exc:
            self.state = self._reject(result, PF["PF013"], str(exc))
            return result
        required_margin = estimated_notional / intent.leverage
        if required_margin > account.available_margin:
            self.state = self._reject(result, PF["PF017"], f"Required margin {required_margin} exceeds available margin {account.available_margin}.")
            return result
        if self.risk_manager and not self.risk_manager.validate_risk(account, intent, metadata):
            self.state = self._reject(result, "RISK_VALIDATION_FAILED", "Order rejected by risk manager.")
            return result

        self.state = PreFlightState.RISK_CHECKED
        self.state = PreFlightState.AUTHORIZED
        return result


class RiskStub:
    def __init__(self, halted=False, approve=True):
        self._halted = halted
        self._approve = approve

    def is_trading_halted(self):
        return self._halted

    def validate_risk(self, account, intent, metadata):
        return self._approve


def make_intent(**kw):
    base = dict(
        instrument_id="ETH/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("2500"),
        size=Decimal("0.01"),
        leverage=Decimal("2"),
    )
    base.update(kw)
    return OrderIntent(**base)


def make_metadata(**kw):
    base = dict(
        symbol="ETH/USDT:USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.1"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("0.01"),
        contract_type="linear",
        is_live=True,
    )
    base.update(kw)
    return InstrumentMetadata(**base)


def make_account(**kw):
    base = dict(
        balance=Decimal("1000"),
        available_margin=Decimal("1000"),
        leverage=Decimal("10"),
    )
    base.update(kw)
    return AccountState(**base)


def make_market(**kw):
    base = dict(
        bid=Decimal("2500"),
        ask=Decimal("2500"),
        last=Decimal("2500"),
        timestamp=time.time(),
    )
    base.update(kw)
    return MarketData(**base)


def run_matrix():
    kill_switch_values = [False, True]
    risk_variants = [
        None,
        RiskStub(halted=False, approve=True),
        RiskStub(halted=True, approve=True),
        RiskStub(halted=False, approve=False),
    ]
    metadata_variants = [
        None,
        make_metadata(),
        make_metadata(symbol="OTHER/USDT:USDT"),
        make_metadata(is_live=False),
        make_metadata(tick_size=Decimal("0")),
        make_metadata(lot_size=Decimal("0")),
        make_metadata(min_size=Decimal("0")),
        make_metadata(contract_val=Decimal("0")),
        make_metadata(contract_type="weird"),
    ]
    intent_variants = [
        make_intent(),
        make_intent(instrument_id="OTHER/USDT:USDT"),
        make_intent(price=Decimal("0")),
        make_intent(price=Decimal("2500.05")),
        make_intent(size=Decimal("0")),
        make_intent(size=Decimal("0.005")),
        make_intent(size=Decimal("5")),
        make_intent(size=Decimal("0.015")),
        make_intent(leverage=Decimal("0")),
        make_intent(leverage=Decimal("50")),
    ]
    account_variants = [
        None,
        make_account(),
        make_account(leverage=Decimal("0")),
        make_account(available_margin=Decimal("0")),
        make_account(available_margin=Decimal("0.0001")),
    ]
    market_variants = [
        None,
        make_market(),
        make_market(last=Decimal("0")),
        make_market(timestamp=time.time() - 9999),
    ]

    checked = 0
    for kill_switch, risk, metadata, intent, account, market in itertools.product(
        kill_switch_values,
        risk_variants,
        metadata_variants,
        intent_variants,
        account_variants,
        market_variants,
    ):
        config.KILL_SWITCH_ACTIVE = kill_switch
        original = OriginalValidator(risk_manager=risk)
        current = PreFlightValidator(risk_manager=risk)

        original_result = original.validate(intent, metadata, account, market)
        current_result = current.validate(intent, metadata, account, market)

        assert original_result.passed == current_result.passed, (
            kill_switch, risk, metadata, intent, account, market
        )
        assert original_result.rejection_code == current_result.rejection_code, (
            original_result.rejection_code,
            current_result.rejection_code,
            kill_switch,
        )
        assert original_result.message == current_result.message, (
            original_result.message,
            current_result.message,
        )
        assert original.state == current.state, (original.state, current.state)
        checked += 1

    config.KILL_SWITCH_ACTIVE = True
    return checked


def test_rule_list_validator_matches_the_original_precedence():
    """The rule list must reject with the same code, message and state.

    The rule list is a refactor of a long sequence of guards. If the order
    changed, a different rejection code would be reported for the same
    input, which would change what the operator sees and what the
    authorization token is bound to.
    """
    checked = run_matrix()
    assert checked > 10_000

