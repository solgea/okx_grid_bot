from dataclasses import dataclass
from enum import Enum


class PromotionState(str, Enum):
    PAPER = "PAPER"
    PROMOTION_PENDING = "PROMOTION_PENDING"
    DEMO = "DEMO"


@dataclass(frozen=True)
class PromotionCheck:
    positions_empty: bool
    orders_empty: bool
    symbol_allowed: bool
    metadata_valid: bool
    risk_defined: bool
    leverage_margin_ok: bool
    is_demo: bool
    human_approved: bool

    @property
    def passed(self) -> bool:
        return all(self.__dict__.values())


class Promotion:
    def __init__(self, seq: int, state: PromotionState = PromotionState.PAPER) -> None:
        self.state = state
        self.seq = seq

    def request(self) -> None:
        if self.state is not PromotionState.PAPER:
            raise ValueError("invalid promotion request")
        self.state = PromotionState.PROMOTION_PENDING

    def approve(self, check: PromotionCheck) -> bool:
        if self.state is not PromotionState.PROMOTION_PENDING or not check.passed:
            self.state = PromotionState.PAPER
            return False
        self.state = PromotionState.DEMO
        return True
