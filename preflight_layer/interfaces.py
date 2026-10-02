from abc import ABC, abstractmethod

from preflight_layer.domain import (
    AccountState,
    InstrumentMetadata,
    MarketData,
    OrderIntent,
    ValidationResult,
)


class IExchangeAdapter(ABC):
    @abstractmethod
    async def fetch_instrument_metadata(self, instrument_id: str) -> InstrumentMetadata:
        raise NotImplementedError

    @abstractmethod
    async def fetch_account_state(self) -> AccountState:
        raise NotImplementedError

    @abstractmethod
    async def fetch_market_data(self, instrument_id: str) -> MarketData:
        raise NotImplementedError


class IRiskManager(ABC):
    """Canonical risk adapter contract used by PreFlightValidator."""

    @abstractmethod
    def validate_risk(self, account: AccountState, intent: OrderIntent) -> bool:
        raise NotImplementedError


class IPreFlightValidator(ABC):
    @abstractmethod
    def validate(self, intent: OrderIntent) -> ValidationResult:
        raise NotImplementedError
