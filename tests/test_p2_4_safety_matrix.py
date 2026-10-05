import copy
from decimal import Decimal
from types import SimpleNamespace
import time

import pytest

from engine.risk_manager import RiskManager
from engine.sync_engine import ExecutionStatus, _classify_batch_result
from preflight_layer.domain import (
    AccountState,
    ExecutionAuthorization,
    InstrumentMetadata,
    MarketData,
    OrderIntent,
    OrderSide,
    OrderType,
)
from preflight_layer.validator import PreFlightValidator


def make_intent(size="0.01"):
    return OrderIntent(
        instrument_id="TEST-USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("10"),
        size=Decimal(size),
        leverage=Decimal("2"),
        client_order_id="test123",
    )


def make_metadata():
    return InstrumentMetadata(
        symbol="TEST-USDT",
        min_size=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.01"),
        contract_val=Decimal("1"),
        contract_type="linear",
        is_live=True,
    )


def make_account(margin="100"):
    return AccountState(
        balance=Decimal("100"),
        available_margin=Decimal(margin),
        leverage=Decimal("5"),
    )


def make_market():
    return MarketData(last=Decimal("10"), timestamp=time.time())


def test_execution_authorization_rejects_mutated_intent():
    intent = make_intent()
    authorization = ExecutionAuthorization.from_authorized_intents([intent])

    mutated = copy.deepcopy(intent)
    mutated.size = Decimal("0.02")

    with pytest.raises(PermissionError):
        authorization.require_for([mutated])


def test_execution_authorization_rejects_count_mismatch():
    authorization = ExecutionAuthorization.from_authorized_intents([make_intent()])

    with pytest.raises(PermissionError):
        authorization.require_for([])


def test_unknown_batch_result_is_not_reclassified_as_rejected():
    result = _classify_batch_result({"info": {"sCode": "0"}})

    assert result is ExecutionStatus.UNKNOWN
    assert result is not ExecutionStatus.REJECTED


def test_explicit_exchange_rejection_is_rejected():
    result = _classify_batch_result({"info": {"sCode": "51008"}})

    assert result is ExecutionStatus.REJECTED


def test_successful_exchange_result_is_success():
    result = _classify_batch_result({"id": "123", "info": {"sCode": "0"}})

    assert result is ExecutionStatus.SUCCESS


def test_zero_balance_cannot_initialize_risk_manager():
    risk = RiskManager()

    with pytest.raises(ValueError):
        risk.initialize_balance(0.0)

    assert risk.trading_halted is True


def test_invalid_contract_metadata_is_fail_closed(monkeypatch):
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    validator = PreFlightValidator()
    metadata = make_metadata()
    metadata.contract_val = Decimal("0")

    result = validator.validate(make_intent(), metadata, make_account(), make_market())

    assert result.passed is False
    assert result.rejection_code == "PF013_INVALID_CONTRACT_VALUE"


def test_insufficient_contract_margin_is_rejected(monkeypatch):
    monkeypatch.setattr("config.settings.config.KILL_SWITCH_ACTIVE", False)
    validator = PreFlightValidator()

    result = validator.validate(
        make_intent(size="0.1"),
        make_metadata(),
        make_account(margin="0.4"),
        make_market(),
    )

    assert result.passed is False
    assert result.rejection_code == "PF017_INSUFFICIENT_MARGIN"
