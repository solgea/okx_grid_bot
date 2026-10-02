import logging
from config.settings import config

logger = logging.getLogger("RiskManager")


class RiskManager:
    def __init__(self):
        self.initial_balance = 0.0
        self.peak_balance = 0.0
        self.daily_starting_balance = 0.0
        self.kill_switch_triggered = False

    def initialize_balance(self, current_balance: float):
        if current_balance <= 0:
            raise ValueError("Risk manager requires a positive starting balance")
        self.initial_balance = current_balance
        self.peak_balance = current_balance
        self.daily_starting_balance = current_balance

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
            logger.critical("Hard position limit breached: %s > %s", abs(current_position_size), config.MAX_POSITION_SIZE)
            return True
        return False
