import hashlib
import json
import logging
from enum import Enum

from config.settings import config

logger = logging.getLogger("RiskManager")
RISK_STATE_VERSION = 1


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
        self.trading_halted = False
        self.safe_haven = 0.0
        self.active_compounding_capital = 0.0
        self.current_regime = RiskRegime.AGGRESSIVE
        self._state_dirty = False
        self.maker_fee = getattr(config, "MAKER_FEE_PCT", 0.0002)
        self.taker_fee = getattr(config, "TAKER_FEE_PCT", 0.0005)
        self.slippage_buffer = getattr(config, "SLIPPAGE_PCT", 0.0001)

    def halt_trading(self, reason: str):
        self.trading_halted = True
        self._state_dirty = True
        logger.critical("Trading halted: %s", reason)

    @property
    def state_dirty(self) -> bool:
        return self._state_dirty

    def mark_state_persisted(self) -> None:
        self._state_dirty = False

    def export_state(self) -> dict:
        state = {
            "initial_balance": self.initial_balance,
            "peak_balance": self.peak_balance,
            "daily_starting_balance": self.daily_starting_balance,
            "kill_switch_triggered": self.kill_switch_triggered,
            "trading_halted": self.trading_halted,
            "safe_haven": self.safe_haven,
            "active_compounding_capital": self.active_compounding_capital,
            "current_regime": self.current_regime.value,
        }
        encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
        return {
            "version": RISK_STATE_VERSION,
            "state": state,
            "checksum": hashlib.sha256(encoded).hexdigest(),
        }

    def restore_state(self, envelope: dict, current_balance: float) -> None:
        if not isinstance(envelope, dict) or envelope.get("version") != RISK_STATE_VERSION:
            self.halt_trading("Risk state version is invalid")
            raise ValueError("Risk state version is invalid")

        state = envelope.get("state")
        checksum = envelope.get("checksum")
        if not isinstance(state, dict) or not isinstance(checksum, str):
            self.halt_trading("Risk state structure is invalid")
            raise ValueError("Risk state structure is invalid")

        encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(encoded).hexdigest() != checksum:
            self.halt_trading("Risk state checksum mismatch")
            raise ValueError("Risk state checksum mismatch")

        required = {
            "initial_balance", "peak_balance", "daily_starting_balance",
            "kill_switch_triggered", "trading_halted", "safe_haven",
            "active_compounding_capital", "current_regime",
        }
        if set(state) != required:
            self.halt_trading("Risk state fields are invalid")
            raise ValueError("Risk state fields are invalid")

        if current_balance <= 0:
            self.halt_trading("Current account balance is invalid")
            raise ValueError("Current account balance is invalid")

        try:
            self.initial_balance = float(state["initial_balance"])
            self.peak_balance = float(state["peak_balance"])
            self.daily_starting_balance = float(state["daily_starting_balance"])
            self.kill_switch_triggered = bool(state["kill_switch_triggered"])
            self.trading_halted = bool(state["trading_halted"])
            self.safe_haven = float(state["safe_haven"])
            self.active_compounding_capital = float(state["active_compounding_capital"])
            self.current_regime = RiskRegime(state["current_regime"])
        except (TypeError, ValueError) as exc:
            self.halt_trading("Risk state values are invalid")
            raise ValueError("Risk state values are invalid") from exc

        if (
            self.initial_balance <= 0
            or self.peak_balance <= 0
            or self.daily_starting_balance < 0
            or self.safe_haven < 0
            or self.active_compounding_capital < 0
        ):
            self.halt_trading("Risk state contains invalid financial values")
            raise ValueError("Risk state contains invalid financial values")

        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        self._evaluate_regime(current_balance)
        self._state_dirty = False

    def initialize_balance(self, current_balance: float):
        if current_balance <= 0:
            self.halt_trading("Invalid or zero account balance")
            raise ValueError("Risk manager requires a positive starting balance")
        self.initial_balance = current_balance
        self.peak_balance = current_balance
        self.daily_starting_balance = current_balance
        self.active_compounding_capital = current_balance
        self._evaluate_regime(current_balance)
        self._state_dirty = True

    def update_after_trade(self, current_balance: float, last_trade_pnl: float):
        if last_trade_pnl > 0 and self.current_regime == RiskRegime.DEFENSIVE:
            self.safe_haven += last_trade_pnl * 0.5
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        self._evaluate_regime(current_balance)
        self._state_dirty = True

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
            self._state_dirty = True
            return True
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
            self._state_dirty = True

        drawdown_pct = (
            ((self.peak_balance - current_balance) / self.peak_balance) * 100
            if self.peak_balance > 0 else 0.0
        )
        daily_loss = self.daily_starting_balance - current_balance

        if drawdown_pct >= config.MAX_DRAWDOWN_PCT or daily_loss >= config.MAX_DAILY_LOSS_USDT:
            self.kill_switch_triggered = True
            self._state_dirty = True
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
