import logging
from enum import Enum

from config.settings import config

logger = logging.getLogger("RiskManager")


class RiskRegime(Enum):
    AGGRESSIVE = "AGGRESSIVE"
    DEFENSIVE = "DEFENSIVE"
    PRESERVATION = "PRESERVATION"


class RiskManager:
    def __init__(self):
        self.initial_balance = 0.0
        self.peak_balance = 0.0
        self.daily_starting_balance = 0.0
        self.kill_switch_triggered = False
        self.safe_haven = 0.0
        self.active_compounding_capital = 0.0
        self.current_regime = RiskRegime.AGGRESSIVE
        self.maker_fee = getattr(config, "MAKER_FEE_PCT", 0.0002)
        self.taker_fee = getattr(config, "TAKER_FEE_PCT", 0.0005)
        self.slippage_buffer = getattr(config, "SLIPPAGE_PCT", 0.0001)

    def initialize_balance(self, current_balance: float):
        if current_balance <= 0:
            raise ValueError("Risk manager requires a positive starting balance")
        self.initial_balance = current_balance
        self.peak_balance = current_balance
        self.daily_starting_balance = current_balance
        self.active_compounding_capital = current_balance
        self._evaluate_regime(current_balance)

    def update_after_trade(self, current_balance: float, last_trade_pnl: float):
        if last_trade_pnl > 0 and self.current_regime == RiskRegime.DEFENSIVE:
            self.safe_haven += last_trade_pnl * 0.5
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        self._evaluate_regime(current_balance)

    def _evaluate_regime(self, current_balance: float):
        drawdown_pct = (
            ((self.peak_balance - current_balance) / self.peak_balance) * 100
            if self.peak_balance > 0 else 0.0
        )
        threshold = getattr(config, "REGIME2_THRESHOLD_USDT", self.initial_balance * 3.0)
        preservation_dd = getattr(config, "REGIME3_DD_LIMIT_PCT", 10.0)

        if drawdown_pct >= preservation_dd:
            self.current_regime = RiskRegime.PRESERVATION
            self.active_compounding_capital = max(0.0, current_balance)
        elif current_balance >= threshold:
            self.current_regime = RiskRegime.DEFENSIVE
            self.active_compounding_capital = max(0.0, current_balance - self.safe_haven)
        else:
            self.current_regime = RiskRegime.AGGRESSIVE
            self.active_compounding_capital = max(0.0, current_balance - self.safe_haven)

    def check_trade_viability(self, entry_price: float, target_price: float, is_maker: bool = True) -> bool:
        if entry_price <= 0 or target_price <= 0:
            return False
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        total_friction = (fee_rate * 2) + self.slippage_buffer
        gross_profit_pct = abs(target_price - entry_price) / entry_price
        return gross_profit_pct - total_friction >= total_friction * 2

    def check_risk_limits(self, current_balance: float, current_position_size: float) -> bool:
        if not config.KILL_SWITCH_ACTIVE:
            return False
        if self.kill_switch_triggered:
            return True
        if current_balance <= 0:
            self.kill_switch_triggered = True
            return True
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance

        drawdown_pct = (
            ((self.peak_balance - current_balance) / self.peak_balance) * 100
            if self.peak_balance > 0 else 0.0
        )
        daily_loss = self.daily_starting_balance - current_balance

        if drawdown_pct >= config.MAX_DRAWDOWN_PCT or daily_loss >= config.MAX_DAILY_LOSS_USDT:
            self.kill_switch_triggered = True
            return True

        if abs(current_position_size) > config.MAX_POSITION_SIZE:
            logger.critical(
                "Hard position limit breached: %s > %s",
                abs(current_position_size), config.MAX_POSITION_SIZE,
            )
            return True
        return False

    def get_allowed_position_size(self) -> float:
        capital = self.active_compounding_capital
        return capital * 0.5 if self.current_regime == RiskRegime.PRESERVATION else capital
