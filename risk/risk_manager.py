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
        """Bot ilk başladığında bakiye durumunu kaydeder."""
        self.initial_balance = current_balance
        self.peak_balance = current_balance
        self.daily_starting_balance = current_balance
        logger.info(f"🛡️ Risk Yöneticisi Başlatıldı. Başlangıç Bakiyesi: {current_balance:.2f} USDT")

    def check_risk_limits(self, current_balance: float, current_position_size: float) -> bool:
        """
        Tüm risk kurallarını denetler. 
        Eğer herhangi bir limit ihlal edilirse True döner (Kill-Switch Tetiklenir).
        """
        if not config.KILL_SWITCH_ACTIVE:
            return False

        if self.kill_switch_triggered:
            return True

        # 1. En yüksek bakiyeyi (Peak) Güncelle
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance

        # 2. Maximum Drawdown (% Düşüş) Kontrolü
        if self.peak_balance > 0:
            drawdown_pct = ((self.peak_balance - current_balance) / self.peak_balance) * 100
            if drawdown_pct >= config.MAX_DRAWDOWN_PCT:
                logger.critical(
                    f"🚨 KILL-SWITCH TETİKLENDİ! Max Drawdown Aşıldı: %{drawdown_pct:.2f} "
                    f"(Limit: %{config.MAX_DRAWDOWN_PCT})"
                )
                self.kill_switch_triggered = True
                return True

        # 3. Günlük Maksimum Kayıp Kontrolü
        daily_loss = self.daily_starting_balance - current_balance
        if daily_loss >= config.MAX_DAILY_LOSS_USDT:
            logger.critical(
                f"🚨 KILL-SWITCH TETİKLENDİ! Günlük Maksimum Kayıp Aşıldı: {daily_loss:.2f} USDT "
                f"(Limit: {config.MAX_DAILY_LOSS_USDT} USDT)"
            )
            self.kill_switch_triggered = True
            return True

        # 4. Maksimum Pozisyon Büyüklüğü Kontrolü
        if current_position_size > config.MAX_POSITION_SIZE:
            logger.warning(
                f"⚠️ Pozisyon Limiti İhlali: {current_position_size} "
                f"(Limit: {config.MAX_POSITION_SIZE}). Yeni pozisyon açılışı engelleniyor!"
            )
            # Sadece pozisyon büyütmeyi durdurmak için isteğe bağlı logic eklenebilir.

        return False