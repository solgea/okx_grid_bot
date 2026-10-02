import requests
import pandas as pd


def get_dynamic_grid_bounds(symbol="config.symbol", timeframe="config.timeframe", limit=100):
    # OKX v5 API'den mum verilerini çek (Şifresiz public endpoint)
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar={timeframe}&limit={limit}"
    
    try:
        response = requests.get(url).json()
        
        if response.get('code') != '0':
            print(f"❌ OKX API Hatası: {response.get('msg')}")
            return None, None
            
        # Gelen veriyi Pandas DataFrame'e çevir
        # OKX formatı: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        data = response['data']
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'vol', 'volCcy', 'volCcyQuote', 'confirm'])
        
        # Sütunları sayısal değere çevir (API'den string döner)
        cols = ['open', 'high', 'low', 'close']
        df[cols] = df[cols].apply(pd.to_numeric)
        
        # DataFrame'i en eskiden en yeniye doğru sırala (Gösterge hesaplamaları için)
        df = df.iloc[::-1].reset_index(drop=True)
        
        # ---------------------------------------------------------
        # YÖNTEM 1: Support/Resistance (Zirve ve Dip) Tabanlı
        # ---------------------------------------------------------
        sr_upper_price = df['high'].max()
        sr_lower_price = df['low'].min()
        
        # ---------------------------------------------------------
        # YÖNTEM 2: ATR Tabanlı Dinamik Range (Kütüphanesiz Saf Pandas)
        # ---------------------------------------------------------
        # True Range (TR) Hesaplaması
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = (df['high'] - df['close'].shift(1)).abs()
        df['tr3'] = (df['low'] - df['close'].shift(1)).abs()
        df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        # 14 Periyotluk Basit ATR Hesaplaması
        df['ATR'] = df['true_range'].rolling(window=14).mean()
        
        current_price = df['close'].iloc[-1]
        current_atr = df['ATR'].iloc[-1]
        
        # ATR çarpanı (Örn: Fiyatın 3 ATR üstü ve altı)
        atr_multiplier = 3.0
        atr_upper_price = current_price + (current_atr * atr_multiplier)
        atr_lower_price = current_price - (current_atr * atr_multiplier)
        
        return {
            "sr_bounds": (sr_lower_price, sr_upper_price),
            "atr_bounds": (atr_lower_price, atr_upper_price),
            "current_price": current_price
        }

    except Exception as e:
        print(f"❌ Veri çekilirken hata oluştu: {e}")
        return None

# --- KULLANIM ---
if __name__ == "__main__":
    bounds = get_dynamic_grid_bounds(symbol="config.SYMBOL", timeframe="config.TIMEFRAME", limit=120)
    
    if bounds:
        print("📊 OKX Dinamik Fiyat Sınırları")
        print(f"Anlık Fiyat: {bounds['current_price']}")
        print("-" * 30)
        print("🔹 Yöntem 1 (Son 120 Mumun Zirve/Dip Noktaları - Order Block Hedefli):")
        print(f"Lower Price: {bounds['sr_bounds'][0]}")
        print(f"Upper Price: {bounds['sr_bounds'][1]}")
        print("-" * 30)
        print("🔸 Yöntem 2 (ATR Tabanlı Volatilite Sınırları):")
        print(f"Lower Price: {bounds['atr_bounds'][0]:.2f}")
        print(f"Upper Price: {bounds['atr_bounds'][1]:.2f}")