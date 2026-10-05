from dataclasses import dataclass

from config.settings import config


@dataclass(frozen=True)
class RiskPolicy:
    max_position_size: float
    max_drawdown_pct: float
    max_daily_loss_usdt: float
    market_data_max_age_sec: float
    max_leverage: float

    @classmethod
    def from_config(cls):
        return cls(
            max_position_size=float(config.MAX_POSITION_SIZE),
            max_drawdown_pct=float(config.MAX_DRAWDOWN_PCT),
            max_daily_loss_usdt=float(config.MAX_DAILY_LOSS_USDT),
            market_data_max_age_sec=float(config.MARKET_DATA_MAX_AGE_SEC),
            max_leverage=float(config.LEVERAGE),
        )
