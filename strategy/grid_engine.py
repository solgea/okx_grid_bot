from decimal import Decimal, ROUND_DOWN, InvalidOperation
from enum import Enum
import uuid
from config.settings import config
# PreFlight Domain modellerimizi içeri alıyoruz
from preflight_layer.domain import OrderIntent, OrderSide, OrderType


class GridState(str, Enum):
    """Grid'in mevcut piyasa/pozisyon bağlamını temsil eden FSM durumları."""

    INITIALIZING = "INITIALIZING"
    READY = "READY"
    ACCUMULATING = "ACCUMULATING"
    DISTRIBUTING = "DISTRIBUTING"
    PAUSED = "PAUSED"
    RISK_OFF = "RISK_OFF"


class GridEngine:
    """Deterministic grid calculations using Decimal arithmetic."""

    @staticmethod
    def _decimal(value) -> Decimal:
        try:
            value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid numeric value: {value!r}") from exc
        if not value.is_finite():
            raise ValueError(f"Numeric value must be finite: {value!r}")
        return value

    def _price_quantum(self) -> Decimal:
        if self.price_precision < 0:
            raise ValueError("price_precision must be non-negative")
        return Decimal("1").scaleb(-self.price_precision)

    def _quantize_price(self, value: Decimal) -> Decimal:
        return value.quantize(self._price_quantum(), rounding=ROUND_DOWN)

    @staticmethod
    def _quantize_size(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN).normalize()

    @property
    def lower_price(self) -> float:
        """Compatibility view; internal range arithmetic uses Decimal."""
        return float(self._lower_price)

    @property
    def upper_price(self) -> float:
        """Compatibility view; internal range arithmetic uses Decimal."""
        return float(self._upper_price)

    @property
    def grid_step(self) -> float:
        """Compatibility view; calculations use the private Decimal value."""
        return float(self._grid_step)

    @property
    def grid_levels(self) -> list[float]:
        """Compatibility view; calculations use private Decimal levels."""
        return [float(level) for level in self._grid_levels]

    def __init__(self, lower_price: float, upper_price: float, grid_count: int, contract_size: float, 
                 price_precision: int = 2, oob_min_width_pct: float = 0.0, oob_buffer_pct: float = 0.0,
                 min_step_pct: float = 0.0020, tp_margin_pct: float = 0.0025):
        """
        Matematiksel Grid Engine - Borsadan (OKX, vs) tamamen izole edilmiştir.
        Komisyon Korumalı (Fee-Protected) Sürüm.
        """
        self._lower_price = self._decimal(lower_price)
        self._upper_price = self._decimal(upper_price)
        self.grid_count = max(2, int(grid_count))
        self.contract_size = self._decimal(contract_size)
        self.price_precision = int(price_precision)

        self.oob_min_width_pct = self._decimal(oob_min_width_pct)
        self.oob_buffer_pct = self._decimal(oob_buffer_pct)
        self.min_step_pct = self._decimal(min_step_pct)
        self.tp_margin_pct = self._decimal(tp_margin_pct)

        self._grid_step = Decimal("0")
        self._grid_levels: list[Decimal] = []
        self.state = GridState.INITIALIZING
        self.previous_state = None
        self.state_reason = "Grid hesaplanıyor"
        self.confluence_score = 0
        
        self._calculate_grid()
        self._transition(GridState.READY, "Grid seviyeleri hazır")

    def _transition(self, state: GridState, reason: str) -> None:
        """FSM durumunu değiştirir; aynı durumda gereksiz geçiş üretmez."""
        if self.state != state:
            self.previous_state = self.state
            self.state = state
        self.state_reason = reason

    def to_state(self) -> dict:
        return {
            "lower_price": float(self._lower_price),
            "upper_price": float(self._upper_price),
            "grid_count": self.grid_count,
            "contract_size": float(self.contract_size),
            "price_precision": self.price_precision,
            "oob_min_width_pct": float(self.oob_min_width_pct),
            "oob_buffer_pct": float(self.oob_buffer_pct),
            "min_step_pct": float(self.min_step_pct),
            "tp_margin_pct": float(self.tp_margin_pct),
            "state": self.state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "state_reason": self.state_reason,
        }

    def restore_state(self, state: dict) -> None:
        """Restore only strategy-owned state; exchange truth remains authoritative."""
        for name in (
            "lower_price", "upper_price", "contract_size", "oob_min_width_pct",
            "oob_buffer_pct", "min_step_pct", "tp_margin_pct",
        ):
            if name in state:
                setattr(self, f"_{name}", self._decimal(state[name]))
        if "price_precision" in state:
            self.price_precision = int(state["price_precision"])
        if "grid_count" in state:
            self.grid_count = max(2, int(state["grid_count"]))
        self._calculate_grid()
        if state.get("state") in {item.value for item in GridState}:
            self.state = GridState(state["state"])
        previous = state.get("previous_state")
        self.previous_state = GridState(previous) if previous in {item.value for item in GridState} else None
        self.state_reason = str(state.get("state_reason", "State restored"))

    def update_state(
        self,
        current_price: float,
        current_position_size: float,
        entry_price: float,
        confluence_score: int | None = None,
    ) -> GridState:
        """
        Piyasa snapshot'ı ve pozisyona göre FSM durumunu günceller.

        Bu metot yan etkili emir işlemi yapmaz; ana döngüdeki kararları
        gözlemlenebilir ve daha sonra durum bazlı optimize edilebilir hale getirir.
        """
        if confluence_score is not None:
            self.confluence_score = max(0, min(100, int(confluence_score)))
        if current_price <= 0 or self._lower_price >= self._upper_price or not self._grid_levels:
            self._transition(GridState.PAUSED, "Geçersiz fiyat veya grid aralığı")
        elif confluence_score is not None and self.confluence_score < 50:
            self._transition(GridState.RISK_OFF, "Kurumsal confluence skoru düşük")
        elif current_position_size == 0:
            self._transition(GridState.READY, "Açık pozisyon yok")
        elif entry_price <= 0:
            self._transition(
                GridState.ACCUMULATING,
                "Pozisyon var ancak geçerli giriş fiyatı yok",
            )
        elif current_position_size > 0:
            self._transition(GridState.DISTRIBUTING, "Long pozisyon için kâr dağıtımı")
        else:
            self._transition(GridState.DISTRIBUTING, "Short pozisyon için kâr dağıtımı")
        return self.state

    def _calculate_grid(self):
        """Calculate grid levels with deterministic Decimal arithmetic."""
        if self._lower_price >= self._upper_price:
            self._grid_step = Decimal("0")
            level = self._quantize_price(self._lower_price)
            self._grid_levels = [level] * self.grid_count
            return

        min_required_step = self.lower_price * self.min_step_pct
        raw_step = (self._upper_price - self._lower_price) / Decimal(self.grid_count - 1)

        if raw_step < min_required_step:
            self._grid_step = min_required_step
            self.grid_count = max(
                2,
                int((self._upper_price - self._lower_price) / self._grid_step) + 1,
            )
        else:
            self._grid_step = raw_step

        self._grid_levels = [
            self._quantize_price(self._lower_price + (Decimal(i) * self._grid_step))
            for i in range(self.grid_count)
        ]

    def update_dynamic_grid_with_atr(self, atr_value: float, multiplier: float, current_price: float):
        """Update the grid around current price using Decimal arithmetic."""
        atr = self._decimal(atr_value)
        mult = self._decimal(multiplier)
        price = self._decimal(current_price)
        if atr <= 0 or mult <= 0:
            return

        half_range = atr * mult
        self._lower_price = price - half_range
        self._upper_price = price + half_range
        self._calculate_grid()

    def update_grid_from_smc(self, smc_data: dict, current_price: float):
        """Smart Money Concepts (SMC) verilerine göre grid günceller."""
        # 13. Test: Eksik SMC verisi
        if not smc_data or not isinstance(smc_data, dict):
            return
            
        vol_prof = smc_data.get('volume_profile', {})
        val = vol_prof.get('VAL')
        vah = vol_prof.get('VAH')
        
        # 14. Test: Bozuk range (VAL > VAH)
        if val is None or vah is None or val >= vah:
            return
            
        lower_bound = self._decimal(val)
        upper_bound = self._decimal(vah)
        
        obs = smc_data.get('order_blocks', {})
        bull_ob = obs.get('bullish_ob')
        bear_ob = obs.get('bearish_ob')
        
        # 15. Test: Çelişkili (Reversed) Order Blocks verilerinde Fallback
        if bull_ob is not None and bear_ob is not None:
            bull = self._decimal(bull_ob)
            bear = self._decimal(bear_ob)
            if bull < bear:
                lower_bound = bull
                upper_bound = bear

        fvg = smc_data.get("fvg")
        if isinstance(fvg, dict) and fvg.get("lower") is not None and fvg.get("upper") is not None:
            fvg_lower = self._decimal(fvg["lower"])
            fvg_upper = self._decimal(fvg["upper"])
            if fvg_lower < fvg_upper:
                if fvg.get("direction") == "bullish":
                    lower_bound = min(lower_bound, fvg_lower)
                elif fvg.get("direction") == "bearish":
                    upper_bound = max(upper_bound, fvg_upper)

        current_price_dec = self._decimal(current_price)
        mss = smc_data.get("mss")
        if mss == "bullish":
            lower_bound = min(lower_bound, current_price_dec)
        elif mss == "bearish":
            upper_bound = max(upper_bound, current_price_dec)

        score = smc_data.get("confluence_score")
        if score is not None:
            self.confluence_score = max(0, min(100, int(score)))
            if self.confluence_score > 80:
                center = self._decimal(smc_data.get("ote", current_price))
                width = (upper_bound - lower_bound) * Decimal("0.6")
                lower_bound = max(lower_bound, center - width / Decimal("2"))
                upper_bound = min(upper_bound, center + width / Decimal("2"))
                
        # 16 & 18. Testler: OOB (Sınır Dışı) ve Dar Aralık Kalkanları
        current_width = upper_bound - lower_bound
        min_width = current_price_dec * self.oob_min_width_pct

        is_oob = current_price_dec < lower_bound or current_price_dec > upper_bound

        if is_oob:
            target_width = max(current_width, min_width)
            lower_bound = current_price_dec - (target_width / Decimal("2"))
            upper_bound = current_price_dec + (target_width / Decimal("2"))
        else:
            if current_width < min_width:
                upper_bound = lower_bound + min_width
                
        self._lower_price = lower_bound
        self._upper_price = upper_bound
        self._calculate_grid()

    def get_target_orders(self, current_price: float, current_position_size: float, entry_price: float, instrument_id: str = config.SYMBOL, confluence_score: int | None = None) -> list:
        """
        Hedef grid emirlerini hesaplar ve PreFlight (Domain) 
        standartlarında OrderIntent nesneleri üretir.
        """
        current_price_dec = self._decimal(current_price)
        position_size_dec = self._decimal(current_position_size)
        entry_price_dec = self._decimal(entry_price)
        self.update_state(current_price_dec, position_size_dec, entry_price_dec, confluence_score)
        if self.state == GridState.RISK_OFF:
            return []
        
        intents = []
        
        pos_dec = position_size_dec
        contract_dec = self.contract_size
        entry_dec = entry_price_dec
        spread_tolerance = self._price_quantum()

        for lvl in self._grid_levels:
            if abs(lvl - current_price_dec) < spread_tolerance:
                continue

            side_str = "buy" if lvl < current_price_dec else "sell"
            amount_dec = contract_dec
            is_take_profit = False # Varsayılan olarak kademe açılışı (Add) kabul et
            
            # --- ÖLÜ BÖLGE (DEAD-ZONE) KÂR AL KORUMASI ---
            if entry_dec > 0 and pos_dec != 0:
                if side_str == "sell" and pos_dec > 0:
                    is_take_profit = True
                    min_tp = entry_dec * (Decimal("1") + self.tp_margin_pct)
                    if lvl >= min_tp:
                        alloc = min(pos_dec, contract_dec)
                        amount_dec = alloc
                        pos_dec -= alloc
                    else:
                        amount_dec = Decimal('0')
                        
                elif side_str == "buy" and pos_dec < 0:
                    is_take_profit = True
                    min_tp = entry_dec * (Decimal("1") - self.tp_margin_pct)
                    if lvl <= min_tp:
                        alloc = min(abs(pos_dec), contract_dec)
                        amount_dec = alloc
                        pos_dec += alloc
            if amount_dec > 0:
                final_amount = self._quantize_size(amount_dec)
                intent = OrderIntent(
                    instrument_id=instrument_id,
                    side=OrderSide.BUY if side_str == "buy" else OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    price=Decimal(str(lvl)),
                    size=final_amount,
                    leverage=Decimal(str(config.LEVERAGE)),
                    margin_mode=config.MARGIN_MODE,
                    position_side="net",
                    reduce_only=is_take_profit,
                    client_order_id=f"grid_{uuid.uuid4().hex[:6]}"
                )
                if is_take_profit:
                    intent.expected_target_price = entry_dec
                else:
                    if side_str == "buy":
                        intent.expected_target_price = lvl + self._grid_step
                    else:
                        intent.expected_target_price = lvl - self._grid_step
                intent.is_maker = True
                intents.append(intent)
        return intents
