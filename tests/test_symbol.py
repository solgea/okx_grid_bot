from config.settings import config
import ccxt

def test_symbol():
    print("🔍 OKX Sembol ve Kontrat Testi Başlıyor...\n")
    
    # Sadece okuma yapacağımız için key'lere gerek yok
    try:
        exchange = ccxt.okx({'enableRateLimit': True})
        exchange.load_markets()
    except Exception as e:
        print(f"❌ Borsaya bağlanılamadı. CCXT yüklü mü? Hata: {e}")
        return

    # 1. Ayarlardaki Sembolü Kontrol Et
    current_symbol = config.SYMBOL
    print(f"📁 settings.py içindeki sembolünüz: '{current_symbol}'")

    # Sembol CCXT'nin desteklediği piyasalar içinde var mı?
    if current_symbol in exchange.markets:
        market = exchange.markets[current_symbol]
        print(f"✅ Başarılı! Sembol OKX'te bulundu ve aktif.")
        print("-" * 40)
        print("📊 SEMBOL BİLGİLERİ:")
        print(f"Tip          : {market['type'].capitalize()}")
        print(f"OKX API Kodu : {market['id']}") # Örn: BTC-USDT-SWAP
        print(f"Min. İşlem   : {market['limits']['amount']['min']} {market['base']}")
        print(f"Kontrat Çarpanı: {market['contractSize']}")
        print("-" * 40)
        
        # 100 Dolar için Test (Kaldıraçsız, saf maliyet)
        print("\n🧮 100$ Kasa İçin Uygunluk Testi:")
        min_amount = market['limits']['amount']['min']
        # Anlık fiyatı (kabaca) alalım
        try:
            ticker = exchange.fetch_ticker(current_symbol)
            price = ticker['last']
            cost = price * min_amount
            print(f"Anlık Fiyat  : {price} USDT")
            print(f"1 Adet (Min) İşlem Maliyeti: ~{cost:.2f} USDT (Kaldıraçsız)")
            if cost > 30:
                print("⚠️ UYARI: Bu sembol 100$ kasa ile 'Grid' kurmak için çok ağır! (Öneri: ETH veya SOL deneyin)")
            else:
                print("✅ 100$ kasa için uygun. Bolca grid açabilirsiniz.")
        except:
            print("Fiyat çekilemedi ama sembol doğru.")

    else:
        print(f"❌ HATA: '{current_symbol}' geçerli bir CCXT sembolü değil!")
        print("\n💡 Önerilen Doğru Formatlar (USDT Vadeli için):")
        print("  - Bitcoin  -> BTC/USDT:USDT")
        print("  - Ethereum -> ETH/USDT:USDT")
        print("  - Solana   -> SOL/USDT:USDT")

if __name__ == "__main__":
    test_symbol()