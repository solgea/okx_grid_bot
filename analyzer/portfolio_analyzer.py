import os
import sys

import numpy as np
import pandas as pd

EXPECTED_COLUMNS = [
    "Timestamp", "Symbol", "Action", "Position_Size",
    "Entry_Price", "Realized_PnL", "Unrealized_PnL",
    "Net_Total_PnL", "Wallet_Balance",
]


def _enable_utf8_output():
    """Allow emoji output on consoles that default to a legacy code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def load_trade_log(file_path):
    """Read the trade journal into a DataFrame, or None when unusable."""
    try:
        # Read once, without a header, so a missing header row can be
        # detected instead of silently shifting the columns.
        df = pd.read_csv(file_path, header=None, sep=None, engine="python")
    except Exception as e:
        print(f"❌ CSV okuma hatası: {e}")
        return None

    if df.empty:
        return None

    first_row = [str(val).strip() for val in df.iloc[0]]
    if "Timestamp" in first_row or "Symbol" in first_row:
        # The first row is a header.
        df.columns = df.iloc[0].str.strip()
        df = df[1:].reset_index(drop=True)
    elif len(df.columns) == len(EXPECTED_COLUMNS):
        # No header row: assume the documented column order.
        df.columns = EXPECTED_COLUMNS
    else:
        print(
            f"❌ Sütun sayısı uyumsuz. Beklenen: {len(EXPECTED_COLUMNS)}, "
            f"Bulunan: {len(df.columns)}"
        )
        return None

    df.columns = df.columns.str.strip()
    return df


def analyze_portfolio(file_path="trade_execution_log.csv"):
    _enable_utf8_output()

    if not os.path.exists(file_path):
        print(f"❌ HATA: Dosya bulunamadı -> '{file_path}'")
        print("Lütfen botun çalışıp en az bir işlem kaydı ürettiğinden emin olun.")
        return

    df = load_trade_log(file_path)
    if df is None:
        if os.path.exists(file_path) and os.path.getsize(file_path) == 0:
            print("⚠️ CSV dosyası boş, henüz veri kaydedilmemiş.")
        return

    # Sayısal Veri Tiplerini Dönüştürme
    numeric_columns = ["Position_Size", "Entry_Price", "Realized_PnL", "Unrealized_PnL", "Net_Total_PnL", "Wallet_Balance"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # Zaman Damgası Dönüşümü ve Çalışma Süresi Hesabı
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    start_time = df['Timestamp'].min()
    end_time = df['Timestamp'].max()
    runtime_str = "Bilinmiyor"
    if pd.notnull(start_time) and pd.notnull(end_time):
        duration = end_time - start_time
        days = duration.days
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        runtime_str = f"{days} Gün, {hours} Saat, {minutes} Dakika"

    # Başlangıç ve Güncel Bakiye
    initial_wallet = df['Wallet_Balance'].iloc[0] - df['Realized_PnL'].iloc[0]
    if initial_wallet <= 0:
        initial_wallet = df['Wallet_Balance'].iloc[0]

    current_wallet = df['Wallet_Balance'].iloc[-1]
    last_realized_pnl = df['Realized_PnL'].iloc[-1]
    last_unrealized_pnl = df['Unrealized_PnL'].iloc[-1]
    last_net_pnl = df['Net_Total_PnL'].iloc[-1]
    
    roi_percent = (last_net_pnl / initial_wallet * 100) if initial_wallet > 0 else 0.0

    # Max Drawdown Hesaplaması (Equity = Bakiye + Açık Kar/Zarar)
    df['Equity'] = df['Wallet_Balance'] + df['Unrealized_PnL']
    df['Peak_Equity'] = df['Equity'].cummax()
    df['Drawdown'] = df['Equity'] - df['Peak_Equity']
    
    # Sıfıra bölünme koruması ile Drawdown Yüzdesi
    df['Drawdown_Pct'] = np.where(df['Peak_Equity'] > 0, (df['Drawdown'] / df['Peak_Equity']) * 100, 0.0)
    
    max_drawdown = df['Drawdown'].min()
    max_drawdown_pct = df['Drawdown_Pct'].min()

    # Kâr / Zarar İşlem İstatistikleri (Profit Factor & Win Rate)
    # Realized PnL değişimlerini takip et
    pnl_diffs = df['Realized_PnL'].diff().dropna()
    winning_trades = pnl_diffs[pnl_diffs > 0]
    losing_trades = pnl_diffs[pnl_diffs < 0]

    total_gross_profit = winning_trades.sum()
    total_gross_loss = abs(losing_trades.sum())
    
    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    total_closed_trades = win_count + loss_count

    win_rate = (win_count / total_closed_trades * 100) if total_closed_trades > 0 else 0.0
    profit_factor = (total_gross_profit / total_gross_loss) if total_gross_loss > 0 else (total_gross_profit if total_gross_profit > 0 else 0.0)

    # Dinamik Aksiyon Dağılımı
    action_counts = df['Action'].value_counts()

    # Terminal Rapor Çıktısı
    print("\n" + "="*56)
    print("📊 ALGORİTMİK İŞLEM PERFORMANS RAPORU")
    print("="*56)
    print(f"⏱️  Çalışma Süresi (Runtime)   : {runtime_str}")
    print(f"📝 Toplam Log Kaydı Sayısı   : {len(df)}")
    print(f"💵 Başlangıç Cüzdan Bakiyesi : {initial_wallet:.2f} USDT")
    print(f"💳 Güncel Cüzdan Bakiyesi    : {current_wallet:.2f} USDT")
    print("-" * 56)
    print(f"📈 Gerçekleşen Kar/Zarar     : {last_realized_pnl:+.2f} USDT")
    print(f"⏳ Açık Kar/Zarar (Unrealized): {last_unrealized_pnl:+.2f} USDT")
    print(f"💰 Net Toplam Kar/Zarar      : {last_net_pnl:+.2f} USDT")
    print(f"🚀 Toplam ROI (%)            : %{roi_percent:+.2f}")
    print("-" * 56)
    print(f"📉 Maksimum Drawdown (MDD)   : {max_drawdown:.2f} USDT (%{max_drawdown_pct:.2f})")
    print(f"⚖️  Profit Factor             : {profit_factor:.2f}")
    print(f"🎯 Kazanma Oranı (Win Rate)  : %{win_rate:.2f} ({win_count} Kazanç / {loss_count} Kayıp)")
    print("-" * 56)
    print("🔄 Dinamik İşlem Dağılımı:")
    for action_name, count in action_counts.items():
        print(f"  • {action_name:<30} : {count}")
    print("="*56 + "\n")

if __name__ == "__main__":
    import sys

    analyze_portfolio(sys.argv[1] if len(sys.argv) > 1 else "trade_execution_log.csv")