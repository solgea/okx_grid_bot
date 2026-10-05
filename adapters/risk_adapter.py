import logging
from decimal import Decimal
from preflight_layer.interfaces import IRiskManager
from engine.risk_manager import RiskManager
from config.settings import config
from preflight_layer.risk_policy import RiskPolicy

logger = logging.getLogger("RiskPreFlightAdapter")

class RiskPreFlightAdapter(IRiskManager):
    def __init__(self, risk_manager: RiskManager):
        """Mevcut RiskManager örneğini adaptöre enjekte ediyoruz."""
        self.rm = risk_manager

    def is_kill_switch_active(self) -> bool:
        """Drawdown veya günlük kayıp limitleri aşıldıysa emri doğrudan reddeder."""
        return self.rm.kill_switch_triggered or self.rm.trading_halted

    def is_trading_halted(self) -> bool:
        """
        Şimdilik FSM'in 'Durduruldu' (Halted) durumlarını kill-switch ile aynı kabul ediyoruz.
        Gelecekte borsa bakımı veya websocket kesintileri için genişletilebilir.
        """
        return self.rm.kill_switch_triggered or self.rm.trading_halted

    def validate_position_limits(self, account, intent) -> bool:
        """
        1. Statik config limitini (MAX_POSITION_SIZE) denetler.
        2. Dinamik risk rejimi sermayesinin aşılıp aşılmadığını denetler (Safe Haven koruması).
        """
        # 1. Statik Config Limiti (Miktar bazlı)
        if hasattr(config, 'MAX_POSITION_SIZE'):
            max_limit = Decimal(str(self.policy.max_position_size))
            
            if intent.size > max_limit:
                logger.error(
                    f"❌ PreFlight REDDİ: Emir boyutu ({intent.size}) "
                    f"maksimum statik pozisyon limitini ({max_limit}) aşıyor!"
                )
                return False
                
        # 2. Projected post-order exposure: current position + open orders + proposal.
        current_exposure = abs(Decimal(str(getattr(account, "current_position_size", 0))))
        open_order_exposure = abs(Decimal(str(getattr(account, "open_order_exposure", 0))))
        proposed_exposure = Decimal("0") if getattr(intent, "reduce_only", False) else abs(intent.size)
        projected_exposure = current_exposure + open_order_exposure + proposed_exposure
        max_exposure = Decimal(str(config.MAX_POSITION_SIZE))

        if projected_exposure > max_exposure:
            logger.error(
                "❌ PreFlight REDDİ: projected exposure (%s) exceeds max exposure (%s).",
                projected_exposure,
                max_exposure,
            )
            return False

        # 3. Dinamik Rejim Sermayesi Limiti (USDT bazlı).
        allowed_capital = Decimal(str(self.rm.get_allowed_position_size()))
        estimated_cost = intent.size * intent.price

        if estimated_cost > allowed_capital:
            logger.error(
                f"❌ PreFlight REDDİ: Emir maliyeti ({estimated_cost:.2f} USDT), "
                f"aktif rejim sermayesini ({allowed_capital:.2f} USDT) aşıyor! "
                f"(Rejim: {self.rm.current_regime.name})"
            )
            return False

        return True
        
    def validate_friction(self, intent) -> bool:
        """
        Maliyet / Beklenen Değer (EV) filtresi.
        Fiyat hareketinden önce komisyon ve kayma maliyetlerinin kârı yok edip etmeyeceğini denetler.
        """
        entry_price = float(intent.price)
        
        # Grid mimarisinde intent nesnesi içinde hedef fiyat (take_profit) bulunmalıdır.
        # Eğer henüz intent nesnesinde yoksa, 'expected_target_price' özelliğini eklemelisiniz.
        target_price = getattr(intent, 'expected_target_price', None)
        
        if not target_price:
            logger.debug("⚠️ Friction filtresi atlandı: intent nesnesinde 'expected_target_price' bulunamadı.")
            return True # Hedef belli değilse es geç (veya strict modda False döndürebilirsiniz)
            
        is_maker = getattr(intent, 'is_maker', True) # Grid limit emirleri varsayılan olarak maker'dır
        
        return self.rm.check_trade_viability(entry_price, target_price, is_maker)

    def validate_risk(self, account, intent) -> bool:
        """
        PreFlightValidator tarafından zorunlu olarak çağrılan ana risk denetimi.
        Tüm alt risk modüllerini (kill-switch, limitler, friction) birleştirir.
        """
        if self.is_kill_switch_active() or self.is_trading_halted():
            logger.error("❌ PreFlight REDDİ: Sistem kill-switch aktif veya alım-satım durduruldu!")
            return False
            
        if not self.validate_position_limits(account, intent):
            return False
            
        if not self.validate_friction(intent):
            # Loglaması check_trade_viability içinde yapıldığı için burada sadece False dönüyoruz
            return False
            
        return True