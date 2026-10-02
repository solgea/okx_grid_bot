import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger("SMCEngine")


@dataclass(slots=True)
class ConfluenceEvent:
    score: int = 0
    liquidity_sweep: str | None = None
    bos: str | None = None
    fvg_status: str = "none"
    volume_support: bool = False


class ConfluenceEventPool:
    def __init__(self, size=64):
        self._available = [ConfluenceEvent() for _ in range(size)]

    def acquire(self):
        return self._available.pop() if self._available else ConfluenceEvent()

    def release(self, event):
        event.score = 0
        event.liquidity_sweep = None
        event.bos = None
        event.fvg_status = "none"
        event.volume_support = False
        self._available.append(event)


class SMCVolumeEngine:
    def __init__(self, value_area_pct=0.70):
        """
        value_area_pct: Hacmin %70'inin döndüğü standart Value Area (Değer Alanı) oranı.
        """
        self.value_area_pct = value_area_pct
        self.confluence_pool = ConfluenceEventPool()
        self._fvg_lifecycle = []

    def analyze_volume_profile(self, df: pd.DataFrame, bins=50):
        """
        Fiyat aralığını dilimlere (bins) böler ve her fiyat seviyesindeki hacmi hesaplar.
        POC (Point of Control), VAH ve VAL değerlerini döndürür.
        """
        if df.empty:
            return None

        # Fiyatları 'bins' sayısına göre grupla
        df['price_bin'] = pd.cut(df['close'], bins=bins)
        volume_by_price = df.groupby('price_bin', observed=False)['volume'].sum()

        # POC (En çok hacmin döndüğü fiyat)
        poc_bin = volume_by_price.idxmax()
        poc_price = poc_bin.mid

        # Toplam hacim ve Değer Alanı (Value Area) hacim hedefi
        total_volume = volume_by_price.sum()
        target_va_volume = total_volume * self.value_area_pct

        # VAH ve VAL hesaplaması (En yoğun hacimden dışa doğru genişleyerek)
        sorted_volumes = volume_by_price.sort_values(ascending=False)
        current_va_volume = 0
        va_bins = []

        for p_bin, vol in sorted_volumes.items():
            va_bins.append(p_bin)
            current_va_volume += vol
            if current_va_volume >= target_va_volume:
                break

        val_price = min([b.left for b in va_bins])
        vah_price = max([b.right for b in va_bins])

        logger.info(f"📊 Volume Profile -> POC: {poc_price:.2f} | VAL: {val_price:.2f} | VAH: {vah_price:.2f}")
        
        return {
            "POC": poc_price,
            "VAL": val_price,
            "VAH": vah_price
        }

    def identify_order_blocks(self, df: pd.DataFrame, impulse_threshold=1.5):
        """
        1 dakikalık mumlardaki sert hareketleri (Impulsive moves) tespit eder.
        Sert yükselişten önceki son düşüş mumu -> Bullish Order Block
        Sert düşüşten önceki son yükseliş mumu -> Bearish Order Block
        """
        # ATR (Average True Range) benzeri basit bir volatilite ölçümü
        df['body'] = abs(df['close'] - df['open'])
        avg_body = df['body'].mean()

        bullish_ob = None
        bearish_ob = None

        # Son mumlardan geriye doğru tarama
        for i in range(len(df) - 1, 1, -1):
            current_body = df['body'].iloc[i]
            is_bullish_impulse = (df['close'].iloc[i] > df['open'].iloc[i]) and (current_body > avg_body * impulse_threshold)
            is_bearish_impulse = (df['close'].iloc[i] < df['open'].iloc[i]) and (current_body > avg_body * impulse_threshold)

            # Bullish Order Block: Sert yükselişten önceki düşüş mumu
            if is_bullish_impulse and bullish_ob is None:
                prev_candle = df.iloc[i-1]
                if prev_candle['close'] < prev_candle['open']: # Düşüş mumuydu
                    bullish_ob = prev_candle['low']
                    
            # Bearish Order Block: Sert düşüşten önceki yükseliş mumu
            if is_bearish_impulse and bearish_ob is None:
                prev_candle = df.iloc[i-1]
                if prev_candle['close'] > prev_candle['open']: # Yükseliş mumuydu
                    bearish_ob = prev_candle['high']

            if bullish_ob and bearish_ob:
                break

        logger.info(f"🏛️ Order Blocks -> Bearish OB (Direnç): {bearish_ob} | Bullish OB (Destek): {bullish_ob}")
        return {"bullish_ob": bullish_ob, "bearish_ob": bearish_ob}

    def analyze_structure(self, df: pd.DataFrame):
        """Return recent FVG zones and a conservative market-structure shift."""
        if len(df) < 3:
            return {"fvg": None, "mss": None}
        bullish_fvg = df.iloc[-3]["high"] < df.iloc[-1]["low"]
        bearish_fvg = df.iloc[-3]["low"] > df.iloc[-1]["high"]
        fvg = None
        if bullish_fvg:
            fvg = {"direction": "bullish", "lower": float(df.iloc[-3]["high"]), "upper": float(df.iloc[-1]["low"])}
        elif bearish_fvg:
            fvg = {"direction": "bearish", "lower": float(df.iloc[-1]["high"]), "upper": float(df.iloc[-3]["low"])}

        prior_high = df["high"].iloc[-5:-2].max() if len(df) >= 5 else df["high"].iloc[:-1].max()
        prior_low = df["low"].iloc[-5:-2].min() if len(df) >= 5 else df["low"].iloc[:-1].min()
        close = float(df.iloc[-1]["close"])
        mss = "bullish" if close > prior_high else "bearish" if close < prior_low else None
        return {"fvg": fvg, "mss": mss}

    def calculate_confluence(self, df: pd.DataFrame, structure=None, volume_profile=None):
        """Score institutional context from confirmed OHLCV data on a 1-100 scale."""
        event = self.confluence_pool.acquire()
        if len(df) < 5:
            return event
        structure = structure or self.analyze_structure(df)
        volume_profile = volume_profile or self.analyze_volume_profile(df)
        last = df.iloc[-1]
        prior = df.iloc[-5:-1]
        recent_high = float(prior["high"].max())
        recent_low = float(prior["low"].min())
        close = float(last["close"])

        if float(last["high"]) > recent_high and close < recent_high:
            event.liquidity_sweep = "bearish"
            event.score += 25
        elif float(last["low"]) < recent_low and close > recent_low:
            event.liquidity_sweep = "bullish"
            event.score += 25

        event.bos = structure.get("mss")
        if event.bos:
            event.score += 20

        fvg = structure.get("fvg")
        if fvg and fvg["lower"] < fvg["upper"]:
            self._fvg_lifecycle.append(dict(fvg, status="formed"))
            event.fvg_status = self._fvg_status(fvg, close)
            if event.fvg_status == "respected":
                event.score += 25
            elif event.fvg_status == "tested":
                event.score += 15

        if volume_profile and volume_profile.get("POC") is not None:
            poc = float(volume_profile["POC"])
            event.volume_support = abs(close - poc) <= max(close * 0.005, 1e-9)
            if event.volume_support:
                event.score += 20
        event.score = max(1, min(100, event.score))
        logger.info("Institutional confluence score=%s", event.score)
        return event

    def _fvg_status(self, fvg, close):
        if fvg["lower"] <= close <= fvg["upper"]:
            return "tested"
        if fvg["direction"] == "bullish" and close > fvg["upper"]:
            return "respected"
        if fvg["direction"] == "bearish" and close < fvg["lower"]:
            return "respected"
        return "filled"