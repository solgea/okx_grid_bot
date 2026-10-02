from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from decimal import Decimal
from enum import Enum
from typing import List, Optional
import time

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"

class PreFlightState(Enum):
    CREATED = "CREATED"
    METADATA_VALIDATED = "METADATA_VALIDATED"
    ACCOUNT_VALIDATED = "ACCOUNT_VALIDATED"
    MARKET_VALIDATED = "MARKET_VALIDATED"
    ORDER_VALIDATED = "ORDER_VALIDATED"
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"

@dataclass
class InstrumentMetadata:
    instrument_id: str
    instrument_type: str
    instrument_state: str
    base_currency: str
    quote_currency: str
    settlement_currency: str
    tick_size: Decimal
    lot_size: Decimal
    min_size: Decimal
    contract_value: Decimal
    contract_value_currency: str
    contract_type: str
    max_limit_order_size: Decimal
    max_market_order_size: Decimal
    max_leverage: Decimal
    listing_time: int
    expiry_time: Optional[int]
    metadata_timestamp: int

@dataclass
class AccountState:
    account_mode: str
    position_mode: str
    margin_mode: str
    equity: Decimal
    available_balance: Decimal
    used_margin: Decimal
    current_leverage: Decimal
    maintenance_margin: Decimal
    initial_margin: Decimal
    open_position_size: Decimal
    open_position_notional: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal

@dataclass
class MarketData:
    last_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    mark_price: Decimal
    index_price: Decimal
    timestamp: int

@dataclass
class OrderIntent:
    instrument_id: str
    side: OrderSide
    order_type: OrderType
    price: Optional[Decimal]
    size: Decimal
    leverage: Decimal
    margin_mode: str
    position_side: str
    reduce_only: bool
    client_order_id: str

@dataclass
class ValidationCheck:
    name: str
    passed: bool
    severity: str
    code: str
    message: str
    actual_value: str
    expected_value: str

@dataclass
class ValidationResult:
    passed: bool
    checks: List[ValidationCheck] = field(default_factory=list)
    rejection_code: Optional[str] = None
    message: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

class IExchangeAdapter(ABC):
    """
    Borsa adaptörlerinin (örn: OKXPreFlightAdapter) uyması gereken şablon (Interface).
    PreFlight katmanı borsadan verileri bu standart metodlarla çeker.
    """
    
    @abstractmethod
    async def fetch_instrument_metadata(self, instrument_id: str) -> InstrumentMetadata:
        pass

    @abstractmethod
    async def fetch_account_state(self) -> AccountState:
        pass

    @abstractmethod
    async def fetch_market_data(self, instrument_id: str) -> MarketData:
        pass

class IRiskManager(ABC):
    """Risk yönetimi ve preflight validasyon adaptörleri için soyut arayüz."""
    
    @abstractmethod
    def validate_risk(self, intent: OrderIntent, account: AccountState) -> ValidationResult:
        pass

class IPreFlightValidator(ABC):
    """Sipariş doğrulama katmanı soyut arayüzü."""
    
    @abstractmethod
    def validate(self, intent: OrderIntent) -> ValidationResult:
        pass