from pydantic_settings import BaseSettings, SettingsConfigDict

NATIVE_SYMBOL = "ETH-USDT-SWAP"
CCXT_SYMBOL = "ETH/USDT:USDT"
BAR_TIMEFRAME = "15m"


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

    SYMBOL: str = CCXT_SYMBOL
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


config = Settings()
