from decimal import Decimal, ROUND_DOWN
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
    def __init__(self, lower_price: float, upper_price: float, grid_count: int, contract_size: float, 
                 price_precision: int = 2, oob_min_width_pct: float = 0.0, oob_buffer_pct: float = 0.0,
                 min_step_pct: float = 0.0020, tp_margin_pct: float = 0.0025):
        """
        Matematiksel Grid Engine - Borsadan (OKX, vs) tamamen izole edilmiştir.
        Komisyon Korumalı (Fee-Protected) Sürüm.
        """
        self.lower_price = float(lower_price)
        self.upper_price = float(upper_price)
        self.grid_count = max(2, int(grid_count))
        self.contract_size = float(contract_size)
        self.price_precision = price_precision
        
        self.oob_min_width_pct = oob_min_width_pct
        self.oob_buffer_pct = oob_buffer_pct
        
        # Komisyon kalkanı parametreleri
        self.min_step_pct = min_step_pct       # İki grid arası minimum %0.20 mesafe (Komisyonu aşmak için)
        self.tp_margin_pct = tp_margin_pct     # Giriş fiyatından en az %0.25 uzakta kâr al (Net kâr için)
        
        self.grid_step = 0.0
        self.grid_levels = []
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
            "lower_price": self.lower_price,
            "upper_price": self.upper_price,
            "grid_count": self.grid_count,
            "contract_size": self.contract_size,
            "price_precision": self.price_precision,
            "oob_min_width_pct": self.oob_min_width_pct,
            "oob_buffer_pct": self.oob_buffer_pct,
            "min_step_pct": self.min_step_pct,
            "tp_margin_pct": self.tp_margin_pct,
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
                setattr(self, name, float(state[name]))
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
        if current_price <= 0 or self.lower_price >= self.upper_price or not self.grid_levels:
            self._transition(GridState.PAUSED, "Geçersiz fiyat veya grid aralığı")
        elif self.confluence_score < 50:
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
        """Alt ve üst sınırlara göre grid adımlarını hesaplar (Komisyon Korumalı)."""
        # 3. Test: Hatalı fiyat aralığı (lower >= upper) koruması
        if self.lower_price >= self.upper_price:
            self.grid_step = 0.0
            self.grid_levels = [round(self.lower_price, self.price_precision)] * self.grid_count
            return
            
        # --- KOMİSYON KORUMASI ---
        min_required_step = self.lower_price * self.min_step_pct
        raw_step = (self.upper_price - self.lower_price) / (self.grid_count - 1)
        
        if raw_step < min_required_step:
            # Hesaplanan aralık komisyonu kurtarmıyorsa, step'i minimuma sabitleyip grid sayısını azaltıyoruz
            self.grid_step = min_required_step
            self.grid_count = max(2, int((self.upper_price - self.lower_price) / self.grid_step) + 1)
        else:
            self.grid_step = raw_step
            
        self.grid_levels = []
        
        for i in range(self.grid_count):
            lvl = self.lower_price + (i * self.grid_step)
            # 4. Test: Precision sorunlarını çözmek için yuvarlama
            self.grid_levels.append(round(lvl, self.price_precision))

    def update_dynamic_grid_with_atr(self, atr_value: float, multiplier: float, current_price: float):
        """Volatiliteye (ATR) dayalı dinamik ızgara güncellemesi."""
        # 5, 6, 7, 8. Testler: Negatif veya sıfır değer koruması
        if atr_value <= 0 or multiplier <= 0:
            return
            
        half_range = atr_value * multiplier
        self.lower_price = current_price - half_range
        self.upper_price = current_price + half_range
        
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
            
        lower_bound = val
        upper_bound = vah
        
        obs = smc_data.get('order_blocks', {})
        bull_ob = obs.get('bullish_ob')
        bear_ob = obs.get('bearish_ob')
        
        # 15. Test: Çelişkili (Reversed) Order Blocks verilerinde Fallback
        if bull_ob is not None and bear_ob is not None:
            if bull_ob < bear_ob:
                lower_bound = bull_ob
                upper_bound = bear_ob

        fvg = smc_data.get("fvg")
        if isinstance(fvg, dict) and fvg.get("lower") < fvg.get("upper"):
            if fvg.get("direction") == "bullish":
                lower_bound = min(lower_bound, fvg["lower"])
            elif fvg.get("direction") == "bearish":
                upper_bound = max(upper_bound, fvg["upper"])

        mss = smc_data.get("mss")
        if mss == "bullish":
            lower_bound = min(lower_bound, current_price)
        elif mss == "bearish":
            upper_bound = max(upper_bound, current_price)

        score = smc_data.get("confluence_score")
        if score is not None:
            self.confluence_score = max(0, min(100, int(score)))
            if self.confluence_score > 80:
                center = float(smc_data.get("ote", current_price))
                width = (upper_bound - lower_bound) * 0.6
                lower_bound = max(lower_bound, center - width / 2)
                upper_bound = min(upper_bound, center + width / 2)
                
        # 16 & 18. Testler: OOB (Sınır Dışı) ve Dar Aralık Kalkanları
        current_width = upper_bound - lower_bound
        min_width = current_price * self.oob_min_width_pct
        
        is_oob = current_price < lower_bound or current_price > upper_bound
        
        if is_oob:
            target_width = max(current_width, min_width)
            lower_bound = current_price - (target_width / 2)
            upper_bound = current_price + (target_width / 2)
        else:
            if current_width < min_width:
                upper_bound = lower_bound + min_width
                
        self.lower_price = lower_bound
        self.upper_price = upper_bound
        self._calculate_grid()

    def get_target_orders(self, current_price: float, current_position_size: float, entry_price: float, instrument_id: str = config.SYMBOL, confluence_score: int | None = None) -> list:
        """
        Hedef grid emirlerini hesaplar ve PreFlight (Domain) 
        standartlarında OrderIntent nesneleri üretir.
        """
        self.update_state(current_price, current_position_size, entry_price, confluence_score)
        if self.state == GridState.RISK_OFF:
            return []
        intents = []
        
        pos_dec = Decimal(str(current_position_size))
        contract_dec = Decimal(str(self.contract_size))
        entry_dec = Decimal(str(entry_price))
        
        for lvl in self.grid_levels:
            # 9. Test: Fiyat tam şu anki grid seviyesindeyse (Spread koruması) atla
            if abs(lvl - current_price) < 0.0001:
                continue
                
            side_str = "buy" if lvl < current_price else "sell"
            amount_dec = contract_dec
            is_take_profit = False # Varsayılan olarak kademe açılışı (Add) kabul et
            
            # --- ÖLÜ BÖLGE (DEAD-ZONE) KÂR AL KORUMASI ---
            if entry_dec > 0 and pos_dec != 0:
                if side_str == "sell" and pos_dec > 0:
                    is_take_profit = True
                    min_tp = float(entry_dec) * (1 + self.tp_margin_pct)
                    if lvl >= min_tp:
                        alloc = min(pos_dec, contract_dec)
                        amount_dec = alloc
                        pos_dec -= alloc
                    else:
                        amount_dec = Decimal('0')
                        
                elif side_str == "buy" and pos_dec < 0:
                    is_take_profit = True
                    min_tp = float(entry_dec) * (1 - self.tp_margin_pct)
                    if lvl <= min_tp:
                        alloc = min(abs(pos_dec), contract_dec)
                        amount_dec = alloc
                        pos_dec += alloc
                    else:
                        amount_dec = Decimal('0')
            
            if amount_dec > 0:
                # Lot limitine (ROUND_DOWN garantisi) Decimal seviyesinde yuvarlama
                final_amount = amount_dec.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN).normalize()
                
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
                
                # --- YENİ: FRICTION FILTER (Risk Adapter) İÇİN HEDEF FİYAT ENJEKSİYONU ---
                if is_take_profit:
                    # Kapatma emri (TP) ise, kârımızı bu seviye (lvl) ile asıl giriş fiyatı (entry) arasında hesaplarız.
                    intent.expected_target_price = float(entry_dec)
                else:
                    # Yeni giriş emri (Add) ise, hedef kârımız grid'in bir sonraki seviyesi kadardır.
                    if side_str == "buy":
                        intent.expected_target_price = lvl + self.grid_step
                    else:
                        intent.expected_target_price = lvl - self.grid_step
                        
                # Limit emirleri tahtaya yazıldığı için maker kabul edilir
                intent.is_maker = True 
                # -------------------------------------------------------------------------

                intents.append(intent)
                
        return intents