# OKX Agent Desk (Paper Trading)

OKX swap ajanlarını yönetmek için Türkçe, yerel çalışan MVP. Herkese açık `ETH-USDT-SWAP` fiyatından ayrı sanal paper portföyü ve isteğe bağlı OKX Demo hesap paneli sunar. Paper portföyü `data/paper_state.json` dosyasında saklanır.

## Çalıştırma

```powershell
python app.py
```

Tarayıcıdan [http://127.0.0.1:8000](http://127.0.0.1:8000) adresini açın. Sunucu yalnızca bu bilgisayardan erişilebilir (`127.0.0.1`). `Ctrl+C` ile durdurun. Demo hesabı için uygulama `.env` içindeki anahtarları kullanır; bu anahtarları sohbette veya sayfada paylaşmayın.

## OKX Demo emirleri

- `.env` içinde `API_KEY`, `API_SECRET`, `PASSPHRASE` ve `IS_DEMO=true` ayarlanmalıdır. Demo Trading ortamında üretilmiş, okuma ve emir yetkili; para çekme yetkisi olmayan anahtar kullanın.
- Demo paneli Demo hesabının USDT bakiyesini, ETH-USDT-SWAP pozisyonlarını ve bekleyen emirlerini ayrı gösterir. API anahtarı ve passphrase arayüze veya API yanıtlarına gönderilmez.
- Limit ve market emirleri her gönderim öncesi onay penceresi gösterir; backend de onay bayrağını zorunlu tutar. Uygulama başına emir miktarı en fazla `1` kontrattır.
- Bu panel kaldıraç veya marjin ayarını değiştirmez ve ana botun strateji emir döngüsünü başlatmaz. Ana botu ayrıca çalıştırmak için bu README'deki dashboard komutunu kullanmayın; `main.py` ayrı bir programdır.
- `IS_DEMO` kapalıysa Demo emri gönderilemez. Canlı hesap/gerçek para emri bu panelden desteklenmez.
- Yerel arayüz Demo API anahtarlarını API yanıtlarına koymaz; emir POST isteklerinde JSON içerik türünü ve aynı-origin tarayıcı isteklerini denetler.

## Paper ajanları

- Sanal başlangıç bakiyesi 10.000 USDT.
- `ETH-USDT-SWAP` için 1 kontrat = `0,01 ETH`.
- Elle paper long/short emri verin veya EMA 9/21 kesişimiyle çalışan otomatik ajan oluşturun.
- Ajan başına kaldıraç `1x-5x`, emir miktarı `1-100` kontrat; en fazla 10 ajan.
- Simülasyonda `%0,05` komisyon uygulanır. Ajan, başlangıç bakiyesinin `%10`'u kadar zararda pozisyonu kapatıp durur.
- Ajan, pozisyon, bakiye ve son işlemler uygulama yeniden başlatıldığında korunur.
- OKX'ten güncel fiyat gelmeden emir veya ajan başlatılamaz; veri eskidiğinde yeni işlemler engellenir.

Paper portföyü ile OKX Demo hesabı birbirinden ayrıdır: paper işlemler yereldir; onaylanan Demo emirleri OKX'in Demo ortamına gönderilir. EMA ajanı yalnızca paper ortamında çalışan kural tabanlı bir ajandır, LLM/üretken yapay zekâ değildir. Gerçek AI modeli veya canlı emir bağlantısı ayrı ve açıkça onaylanan bir geliştirme gerektirir. Simülasyon/Demo sonuçları canlı performansı öngörmez; yatırım tavsiyesi değildir.

## Testler

```powershell
python -m pytest -q tests/test_paper_trading.py tests/test_demo_trading.py
```
