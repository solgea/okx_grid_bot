import pandas as pd
from loguru import logger

class MarketAnalyzer:
    def __init__(self, atr_period=14, volume_multiplier=1.5):
        self.atr_period = atr_period
        self.vol_multiplier = volume_multiplier

    def analyze_1m_data(self, ohlcv_data: list) -> dict:
        """
        OKX'ten gelen ham 1 dakikalık mum verilerini analiz eder.
        ohlcv_data formatı: [timestamp, open, high, low, close, volume]
        """
        try:
            # 1. Veriyi Pandas DataFrame'e çevir ve tipleri ayarla
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            # 2. SAF PANDAS İLE ATR HESAPLAMA (Dış kütüphane olmadan)
            df['tr0'] = abs(df['high'] - df['low'])
            df['tr1'] = abs(df['high'] - df['close'].shift())
            df['tr2'] = abs(df['low'] - df['close'].shift())
            df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
            
            # TradingView uyumlu Wilder's Smoothing (RMA) ile ATR
            df['atr'] = df['tr'].ewm(alpha=1/self.atr_period, min_periods=self.atr_period, adjust=False).mean()
            current_atr = df['atr'].iloc[-1]

            # 3. KURUMSAL HACİM PATLAMASI TESPİTİ
            avg_volume = df['volume'].rolling(window=20).mean().iloc[-2]
            current_volume = df['volume'].iloc[-1]
            volume_spike = current_volume > (avg_volume * self.vol_multiplier)
            
            # Dinamik grid yapısı için hacim şiddetini hesapla
            vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # 4. LİKİDİTE TEMİZLİĞİ (Liquidity Sweep) TESPİTİ
            last_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]
            
            is_bullish_sweep = (last_candle['low'] < prev_candle['low']) and (last_candle['close'] > prev_candle['low'])
            is_bearish_sweep = (last_candle['high'] > prev_candle['high']) and (last_candle['close'] < prev_candle['high'])

            # 5. SİNYAL ÜRETİMİ
            action = "WAIT"
            if is_bullish_sweep and volume_spike:
                action = "LONG"
            elif is_bearish_sweep and volume_spike:
                action = "SHORT"

            current_price = last_candle['close']

            return {
                "action": action,
                "price": current_price,
                "atr": current_atr,
                "vol_ratio": vol_ratio,
                "timestamp": last_candle['timestamp']
            }

        except Exception as e:
            logger.error(f"❌ Analiz motoru hatası: {e}")
            return {"action": "WAIT", "price": 0.0, "atr": 0.0, "vol_ratio": 1.0, "timestamp": 0}