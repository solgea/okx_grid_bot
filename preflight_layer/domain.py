from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal
from typing import Optional, List

# --- ENUM TANIMLARI ---
class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"

class PreFlightState(str, Enum):
    CREATED = "CREATED"
    METADATA_VALIDATED = "METADATA_VALIDATED"
    RISK_CHECKED = "RISK_CHECKED"
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"

# --- DOMAIN VERİ MODELLERİ (DATACLASSES) ---
@dataclass
class OrderIntent:
    instrument_id: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    size: Decimal
    leverage: Decimal = Decimal("10")
    margin_mode: str = "cross"
    position_side: str = "net"
    reduce_only: bool = False
    client_order_id: str = ""

@dataclass
class InstrumentMetadata:
    symbol: str = ""
    min_size: Decimal = Decimal("0.01")
    tick_size: Decimal = Decimal("0.01")
    lot_size: Decimal = Decimal("0.01")
    contract_val: Decimal = Decimal("1")
    is_live: bool = True

@dataclass
class AccountState:
    balance: Decimal = Decimal("0.0")
    available_margin: Decimal = Decimal("0.0")
    leverage: Decimal = Decimal("10")

@dataclass
class MarketData:
    bid: Decimal = Decimal("0.0")
    ask: Decimal = Decimal("0.0")
    last: Decimal = Decimal("0.0")
    timestamp: float = 0.0

@dataclass
class ValidationCheck:
    check_name: str
    passed: bool
    message: str = ""

@dataclass
class ValidationResult:
    passed: bool
    rejection_code: Optional[str] = None
    message: str = ""
    checks: List[ValidationCheck] = field(default_factory=list)

# --- PREFLIGHT RED KODLARI (REJECTION CODES) ---
PF001_INVALID_INSTRUMENT = "PF001_INVALID_INSTRUMENT"
PF002_INSTRUMENT_NOT_LIVE = "PF002_INSTRUMENT_NOT_LIVE"
PF003_INVALID_METADATA = "PF003_INVALID_METADATA"
PF004_INVALID_TICK_SIZE = "PF004_INVALID_TICK_SIZE"
PF005_INVALID_LOT_SIZE = "PF005_INVALID_LOT_SIZE"
PF006_INVALID_MIN_SIZE = "PF006_INVALID_MIN_SIZE"
PF007_INVALID_PRICE = "PF007_INVALID_PRICE"
PF008_PRICE_TICK_MISMATCH = "PF008_PRICE_TICK_MISMATCH"
PF009_INVALID_QUANTITY = "PF009_INVALID_QUANTITY"
PF010_QUANTITY_BELOW_MIN = "PF010_QUANTITY_BELOW_MIN"
PF011_QUANTITY_LOT_MISMATCH = "PF011_QUANTITY_LOT_MISMATCH"
PF012_INVALID_CONTRACT = "PF012_INVALID_CONTRACT"
PF013_INVALID_CONTRACT_VALUE = "PF013_INVALID_CONTRACT_VALUE"
PF014_INVALID_CONTRACT_TYPE = "PF014_INVALID_CONTRACT_TYPE"
PF015_INVALID_LEVERAGE = "PF015_INVALID_LEVERAGE"
PF016_LEVERAGE_EXCEEDED = "PF016_LEVERAGE_EXCEEDED"
PF017_INSUFFICIENT_MARGIN = "PF017_INSUFFICIENT_MARGIN"
PF018_MAX_SIZE_EXCEEDED = "PF018_MAX_SIZE_EXCEEDED"
PF019_POSITION_LIMIT = "PF019_POSITION_LIMIT"
PF020_INVENTORY_LIMIT = "PF020_INVENTORY_LIMIT"
PF021_NOTIONAL_LIMIT = "PF021_NOTIONAL_LIMIT"
PF022_MARGIN_LIMIT = "PF022_MARGIN_LIMIT"
PF023_DRAWDOWN_LIMIT = "PF023_DRAWDOWN_LIMIT"
PF024_DAILY_LOSS_LIMIT = "PF024_DAILY_LOSS_LIMIT"
PF025_STALE_MARKET_DATA = "PF025_STALE_MARKET_DATA"
PF026_MARKET_DATA_UNAVAILABLE = "PF026_MARKET_DATA_UNAVAILABLE"
PF027_ACCOUNT_CONFIGURATION_INVALID = "PF027_ACCOUNT_CONFIGURATION_INVALID"
PF028_POSITION_MODE_MISMATCH = "PF028_POSITION_MODE_MISMATCH"
PF029_KILL_SWITCH = "PF029_KILL_SWITCH"
PF030_TRADING_HALTED = "PF030_TRADING_HALTED"
PF031_API_HEALTH_FAILURE = "PF031_API_HEALTH_FAILURE"
PF999_PREFLIGHT_UNKNOWN_ERROR = "PF999_PREFLIGHT_UNKNOWN_ERROR"