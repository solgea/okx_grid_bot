from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYMBOL = "ETH/USDT:USDT"
BAR_TIMEFRAME = "15m"


def to_native_symbol(ccxt_symbol: str) -> str:
    """Convert a CCXT unified symbol into the native OKX instrument id.

    "ETH/USDT:USDT" -> "ETH-USDT-SWAP". Fails closed on any symbol that is
    not a unified BASE/QUOTE:SETTLE contract.
    """
    base, separator, remainder = ccxt_symbol.partition("/")
    quote = remainder.partition(":")[0]
    if not separator or not base or not quote:
        raise ValueError(
            f"SYMBOL must look like 'BASE/QUOTE:SETTLE' (got {ccxt_symbol!r})"
        )
    return f"{base}-{quote}-SWAP"


class Settings(BaseSettings):
    """Central runtime, exchange and risk configuration."""

    API_KEY: str = ""
    API_SECRET: str = ""
    PASSPHRASE: str = ""

    # Safety defaults: an explicit .env value is required to leave simulation.
    IS_DEMO: bool = True
    DRY_RUN: bool = True
    LIVE_TRADING_ENABLED: bool = False
    LIVE_TRADING_AUTHORIZED: bool = False
    EMERGENCY_FLATTEN_ENABLED: bool = False
    EMERGENCY_FLATTEN_AUTHORIZED: bool = False

    SYMBOL: str = DEFAULT_SYMBOL
    LEVERAGE: int = 10
    MARGIN_MODE: str = "cross"
    TIMEFRAME: str = BAR_TIMEFRAME

    LOWER_PRICE: float = 2500.0
    UPPER_PRICE: float = 2800.0
    GRID_COUNT: int = 10
    CONTRACT_SIZE: float = 0.01

    MAX_POSITION_SIZE: float = 0.1
    MAX_DRAWDOWN_PCT: float = 20.0
    MAX_DAILY_LOSS_USDT: float = 500.0
    KILL_SWITCH_ACTIVE: bool = True

    REGIME2_THRESHOLD_USDT: float = 300.0
    REGIME3_DD_LIMIT_PCT: float = 10.0

    MAKER_FEE_PCT: float = 0.0002
    TAKER_FEE_PCT: float = 0.0005
    SLIPPAGE_PCT: float = 0.0001
    MARKET_DATA_MAX_AGE_SEC: float = 30.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("SYMBOL")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        """Reject symbols that cannot be mapped to a native OKX instrument."""
        to_native_symbol(value)
        return value


config = Settings()

# Convenience aliases derived from the effective configuration. These follow
# SYMBOL instead of pinning a hardcoded instrument.
CCXT_SYMBOL = config.SYMBOL
NATIVE_SYMBOL = to_native_symbol(config.SYMBOL)
