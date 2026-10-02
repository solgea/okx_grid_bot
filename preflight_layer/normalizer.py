from abc import ABC, abstractmethod
from typing import Optional
from preflight_layer.domain import InstrumentMetadata, AccountState, MarketData

class IExchangeAdapter(ABC):
    @abstractmethod
    async def fetch_instrument_metadata(self, instrument_id: str) -> Optional[InstrumentMetadata]:
        pass

    @abstractmethod
    async def fetch_account_state(self) -> AccountState:
        pass

    @abstractmethod
    async def fetch_market_data(self, instrument_id: str) -> Optional[MarketData]:
        pass

class IRiskManager(ABC):
    @abstractmethod
    def is_kill_switch_active(self) -> bool:
        pass

    @abstractmethod
    def is_trading_halted(self) -> bool:
        pass
        
    @abstractmethod
    def validate_position_limits(self, account: AccountState, intent) -> bool:
        pass
