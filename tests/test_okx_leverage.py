import pytest
import ccxt.async_support as ccxt
from unittest.mock import AsyncMock, patch

# Not: Kendi OKXEngine sınıfınızı projenizden import edin.
# Örneğin: from exchange.okx_engine import OKXEngine
# Testin anlaşılması için burada örnek bir OKXEngine mock'u varsayıyoruz:

class OKXEngine:
    """OKXEngine sınıfınızın testler için beklenen örnek yapısı"""
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.exchange = ccxt.okx()
        self.exchange.set_leverage = AsyncMock() # API'ye gitmesini engelliyoruz

    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = "cross"):
        if self.dry_run:
            # DRY_RUN modunda API'ye istek gitmez, sadece log basılır
            return True
            
        if leverage <= 0:
            raise ValueError("Kaldıraç (leverage) 0 veya negatif olamaz!")
            
        try:
            # CCXT kütüphanesi üzerinden OKX'e kaldıraç isteği atıyoruz
            await self.exchange.set_leverage(leverage, symbol, {"marginMode": margin_mode})
            return True
        except ccxt.ExchangeError as e:
            # Borsa spesifik hataları (Örn: Maksimum kaldıraç aşıldı) yakalıyoruz
            print(f"Borsa Hatası: {e}")
            return False

# ==========================================
# 🧪 TEST SENARYOLARI
# ==========================================

@pytest.mark.asyncio
async def test_set_leverage_success():
    """1. Geçerli verilerle kaldıracın borsaya başarıyla gönderilmesi"""
    engine = OKXEngine(dry_run=False)
    
    result = await engine.set_leverage(symbol="ETH/USDT:USDT", leverage=10, margin_mode="cross")
    
    assert result is True
    # Borsaya giden fonksiyonun doğru parametrelerle 1 kez çağrıldığından emin ol
    engine.exchange.set_leverage.assert_called_once_with(10, "ETH/USDT:USDT", {"marginMode": "cross"})

@pytest.mark.asyncio
async def test_set_leverage_zero_or_negative():
    """2. Sıfır veya negatif kaldıraç girildiğinde borsa API'sine gitmeden ValueError fırlatılması"""
    engine = OKXEngine(dry_run=False)
    
    with pytest.raises(ValueError, match="0 veya negatif olamaz"):
        await engine.set_leverage(symbol="ETH/USDT:USDT", leverage=0)
        
    with pytest.raises(ValueError):
        await engine.set_leverage(symbol="ETH/USDT:USDT", leverage=-5)
        
    # API'ye kesinlikle istek atılmamış olmalı (Pre-flight check başarılı)
    engine.exchange.set_leverage.assert_not_called()

@pytest.mark.asyncio
async def test_set_leverage_exceeds_max_limit():
    """3. İzin verilen maksimum kaldıraç aşıldığında ccxt.ExchangeError yakalanması"""
    engine = OKXEngine(dry_run=False)
    
    # API'nin hata fırlatmasını simüle ediyoruz (Mocking)
    engine.exchange.set_leverage.side_effect = ccxt.ExchangeError('okx {"code":"58094","msg":"Leverage is too high"}')
    
    # Beklenti: Fonksiyon çökmeyecek, hatayı yakalayıp False dönecek
    result = await engine.set_leverage(symbol="PEPE/USDT:USDT", leverage=150)
    
    assert result is False
    engine.exchange.set_leverage.assert_called_once()

@pytest.mark.asyncio
async def test_set_leverage_in_dry_run_mode():
    """4. DRY_RUN (Demo) modunda API'ye hiçbir istek gitmemesi"""
    engine = OKXEngine(dry_run=True)
    
    result = await engine.set_leverage(symbol="ETH/USDT:USDT", leverage=20)
    
    assert result is True
    # DRY_RUN aktif olduğu için API'ye kesinlikle istek gitmemeli!
    engine.exchange.set_leverage.assert_not_called()