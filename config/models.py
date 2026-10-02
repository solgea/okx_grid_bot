#config/models.py
from pydantic import BaseModel

class PositionState(BaseModel):
    symbol: str
    side: str                # 'long', 'short', veya 'net'
    contracts: float         # Pozisyonun büyüklüğü (coin veya kontrat adedi)
    entry_price: float       # Ortalama giriş fiyatı
    mark_price: float        # Mevcut piyasa fiyatı
    liquidation_price: float # Likidasyon fiyatı (0 ise likidasyon riski yok/çok uzak)
    unrealized_pnl: float    # Gerçekleşmemiş Kâr/Zarar (USDT cinsinden)
    leverage: float          # Kullanılan kaldıraç
    upl_ratio: float         # Kâr/Zarar yüzdesi (Örn: 0.05 -> %5 kâr)