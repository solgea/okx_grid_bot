import logging
from enum import Enum
from config.settings import config

logger = logging.getLogger("RiskManager")

class RiskRegime(Enum):
    AGGRESSIVE = "AGGRESSIVE"        # Sermaye küçükken: Tüm kârı bileşik büyümeye ekle.
    DEFENSIVE = "DEFENSIVE"          # Büyüme sonrası: Kârın %50'sini Safe Haven (Güvenli Kasa) havuzuna al.
    PRESERVATION = "PRESERVATION"    # Drawdown durumu: Riski küçült ve korumaya geç.

class RiskManager:
    def __init__(self):
        # -- Mevcut Kill-Switch Değişkenleri --
        self.initial_balance = 0.0
        self.peak_balance = 0.0
        self.daily_starting_balance = 0.0
        self.kill_switch_triggered = False
        
        # -- YENİ: Grid Risk Rejimi Değişkenleri --
        self.safe_haven = 0.0
        self.active_compounding_capital = 0.0
        self.current_regime = RiskRegime.AGGRESSIVE
        
        # -- YENİ: Sürtünme (Friction) Parametreleri --
        # config üzerinden çekilir, yoksa varsayılan OKX VIP0 değerleri kullanılır
        self.maker_fee = getattr(config, 'MAKER_FEE_PCT', 0.0002)  # %0.02
        self.taker_fee = getattr(config, 'TAKER_FEE_PCT', 0.0005)  # %0.05
        self.slippage_buffer = getattr(config, 'SLIPPAGE_PCT', 0.0001) # %0.01

    def initialize_balance(self, current_balance: float):
        """Bot ilk başladığında bakiye durumunu kaydeder."""
        self.initial_balance = current_balance
        self.peak_balance = current_balance
        self.daily_starting_balance = current_balance
        self.active_compounding_capital = current_balance
        logger.info(f"🛡️ Risk Yöneticisi Başlatıldı. Başlangıç Bakiyesi: {current_balance:.2f} USDT")
        self._evaluate_regime(current_balance)

    def update_after_trade(self, current_balance: float, last_trade_pnl: float):
        """
        Her kapanan işlemden sonra kasayı ve rejimi günceller.
        Bileşik büyümenin kalbi burasıdır.
        """
        # 1. Kâr edilen bir işlemse ve DEFENSIVE rejimdeysek, kârın bir kısmını kilitle
        if last_trade_pnl > 0 and self.current_regime == RiskRegime.DEFENSIVE:
            safe_haven_cut = last_trade_pnl * 0.5  # Kârın %50'sini güvenceye al
            self.safe_haven += safe_haven_cut
            logger.info(f"🏦 [Safe Haven] {safe_haven_cut:.2f} USDT güvenceye alındı. Toplam Ayrılan: {self.safe_haven:.2f} USDT")

        # 2. En yüksek bakiyeyi (Peak) Güncelle
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
            
        # 3. Yeni sermaye durumuna göre rejimi kontrol et
        self._evaluate_regime(current_balance)

    def _evaluate_regime(self, current_balance: float):
        """Sermaye büyüklüğüne ve Drawdown durumuna göre strateji rejimini belirler."""
        drawdown_pct = 0
        if self.peak_balance > 0:
            drawdown_pct = ((self.peak_balance - current_balance) / self.peak_balance) * 100

        # Eşikleri config'ten al, yoksa varsayılan kullan
        regime2_threshold = getattr(config, 'REGIME2_THRESHOLD_USDT', self.initial_balance * 3.0) # Örn: 100 -> 300 USDT
        dd_preservation_limit = getattr(config, 'REGIME3_DD_LIMIT_PCT', 10.0) # %10 çöküşte korumaya geç

        # --- Rejim Karar Ağacı ---
        if drawdown_pct >= dd_preservation_limit:
            if self.current_regime != RiskRegime.PRESERVATION:
                logger.warning(f"📉 Rejim Değişti: CAPITAL PRESERVATION (DD: %{drawdown_pct:.2f}) - Korumaya geçildi!")
            self.current_regime = RiskRegime.PRESERVATION
            self.active_compounding_capital = current_balance # Safe haven dahil edilmiyor
            
        elif current_balance >= regime2_threshold:
            if self.current_regime != RiskRegime.DEFENSIVE:
                logger.info(f"🛡️ Rejim Değişti: DEFENSIVE COMPOUNDING - Kârın %50'si Safe Haven'a aktarılacak.")
            self.current_regime = RiskRegime.DEFENSIVE
            self.active_compounding_capital = current_balance - self.safe_haven
            
        else:
            if self.current_regime != RiskRegime.AGGRESSIVE and self.initial_balance > 0:
                logger.info("🔥 Rejim Değişti: AGGRESSIVE COMPOUNDING - Tam büyüme modu aktif.")
            self.current_regime = RiskRegime.AGGRESSIVE
            self.active_compounding_capital = current_balance - self.safe_haven

    def check_trade_viability(self, entry_price: float, target_price: float, is_maker: bool = True) -> bool:
        """
        [PRE-FLIGHT FRICTION FILTER]
        Emir borsaya gönderilmeden ÖNCE çağrılır. 
        Hedeflenen kâr, komisyon ve kaymayı karşılayıp sisteme pozitif EV bırakıyor mu?
        """
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        
        # Toplam Sürtünme = (Giriş Komisyonu + Çıkış Komisyonu) + Beklenen Kayma
        total_friction = (fee_rate * 2) + self.slippage_buffer
        
        # Brüt Kâr Hedefi
        gross_profit_pct = abs(target_price - entry_price) / entry_price
        
        # Net Kâr
        net_profit_pct = gross_profit_pct - total_friction
        
        # KURAL: Sistemin çalışması için Net Kâr, en az Toplam Maliyetin 2 katı olmalıdır.
        min_required_net = total_friction * 2
        
        if net_profit_pct < min_required_net:
            logger.debug(
                f"🚫 Friction Filtresi Aşılamadı: Brüt Kâr %{gross_profit_pct*100:.3f}, "
                f"Toplam Maliyet %{total_friction*100:.3f}. İşlem iptal edildi."
            )
            return False
            
        return True

    def check_risk_limits(self, current_balance: float, current_position_size: float) -> bool:
        """
        Mevcut Kill-Switch Limitlerinizi aynen koruyan yapı.
        Eğer limit aşılırsa True döner.
        """
        if not config.KILL_SWITCH_ACTIVE:
            return False

        if self.kill_switch_triggered:
            return True

        # Drawdown Kontrolü
        if self.peak_balance > 0:
            drawdown_pct = ((self.peak_balance - current_balance) / self.peak_balance) * 100
            if drawdown_pct >= config.MAX_DRAWDOWN_PCT:
                logger.critical(
                    f"🚨 KILL-SWITCH TETİKLENDİ! Max Drawdown Aşıldı: %{drawdown_pct:.2f} "
                    f"(Limit: %{config.MAX_DRAWDOWN_PCT})"
                )
                self.kill_switch_triggered = True
                return True

        # Günlük Kayıp Kontrolü
        daily_loss = self.daily_starting_balance - current_balance
        if daily_loss >= config.MAX_DAILY_LOSS_USDT:
            logger.critical(
                f"🚨 KILL-SWITCH TETİKLENDİ! Günlük Maksimum Kayıp Aşıldı: {daily_loss:.2f} USDT "
                f"(Limit: {config.MAX_DAILY_LOSS_USDT} USDT)"
            )
            self.kill_switch_triggered = True
            return True

        # Pozisyon Limiti Kontrolü (Rejime göre dinamikleştirilebilir, şimdilik statik)
        if current_position_size > config.MAX_POSITION_SIZE:
            logger.warning(
                f"⚠️ Pozisyon Limiti İhlali: {current_position_size} "
                f"(Limit: {config.MAX_POSITION_SIZE})."
            )
            # Sadece uyarı veriyoruz, sistemi tamamen durdurmaya gerek yok.

        return False

    def get_allowed_position_size(self) -> float:
        """
        Mevcut rejime göre kullanılabilecek sermayeyi (Compounding Capital) döndürür.
        GridEngine, emir boyutlarını ayarlarken bu fonksiyonu referans almalıdır.
        """
        # Rejime göre farklı kaldıraç veya katsayılar uygulanabilir.
        if self.current_regime == RiskRegime.PRESERVATION:
            return self.active_compounding_capital * 0.5  # Çöküşte sermayenin sadece yarısını kullan
        return self.active_compounding_capital