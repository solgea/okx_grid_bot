from pydantic_settings import BaseSettings, SettingsConfigDict

# CCXT formatı (ETH/USDT:USDT) ile OKX Native V5 formatı (ETH-USDT-SWAP) farklıdır.
# Mum verisi çekerken OKX Native formatı kullanmamız gerekir.
NATIVE_SYMBOL = "ETH-USDT-SWAP" 
CCXT_SYMBOL = "ETH/USDT:USDT"
BAR_TIMEFRAME = "15m"

class Settings(BaseSettings):
    """
    Sistemin tüm konfigürasyon ve risk limitlerini barındıran merkez sınıf.
    Güvenlik gerektiren verileri .env dosyasından okur.
    """
    # OKX API Ayarları (Öncelikli olarak .env'den okunur)
    API_KEY: str = ""
    API_SECRET: str = ""
    PASSPHRASE: str = ""
    IS_DEMO: bool = False  # True: Sandbox / False: Canlı

    # Sembol ve Kaldıraç
    SYMBOL: str = CCXT_SYMBOL  # İşlem motoru için CCXT formatını kullanmaya devam ediyoruz
    LEVERAGE: int = 10         # 100 doları 1000 dolar gibi kullanacağız
    MARGIN_MODE: str = "cross"
    TIMEFRAME: str = BAR_TIMEFRAME # Daha az gürültü, daha güçlü trendler

    # --- DİNAMİK SINIRLAR ---
    # Import anında çökme yaratan ağ çağrısı kaldırıldı. 
    # API çökmesi veya başlangıç durumu için makul manuel sınırlar varsayılan olarak belirlendi.
    # Gerçek dinamik sınırlar botun asenkron başlatılma sürecinde güncellenecektir.
    LOWER_PRICE: float = 2500.0
    UPPER_PRICE: float = 2800.0
    
    GRID_COUNT: int = 10           # 100 Dolar ve ETH ile rahatlıkla 10 kademe açabiliriz!
    CONTRACT_SIZE: float = 0.01    # Minimum ETH kontrat boyutu (1 Kademe = 0.01 ETH)

    # Risk & Safety Limitleri
    MAX_POSITION_SIZE: float = 0.1 # 10 Grid x 0.01 ETH = Maksimum 0.1 ETH tutulabilir
    MAX_DRAWDOWN_PCT: float = 20.0 # 100 dolarda 20 dolar (1/5) riske edilebilir.
    MAX_DAILY_LOSS_USDT: float = 500.0
    KILL_SWITCH_ACTIVE: bool = True

    REGIME2_THRESHOLD_USDT: float = 300.0
    REGIME3_DD_LIMIT_PCT: float = 10.0
    
    # DÜZELTİLEN SATIR BURASI:
    MAKER_FEE_PCT: float = 0.0002          # Borsa komisyonu

    # SİMÜLASYON AYARI
    DRY_RUN: bool = False  # True: Simülasyon (Borsaya emir gitmez) | False: Canlı/Demo İşlem

    # .env entegrasyonu
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Uygulama genelinde kullanılacak olan config nesnesi
config = Settings()