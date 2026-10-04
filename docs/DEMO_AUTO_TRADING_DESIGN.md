# Demo Otomatik İşlem Tasarımı

Durum: **taslak, incelemeye açık**. Bu belge kod değildir; hiçbir emir akışı bu belgeyle açılmaz.

## 1. Amaç ve sınırlar

Dashboard'daki ajanlar, kendi stratejilerinin sinyallerine göre **OKX Demo hesabında** otomatik emir verebilsin.

- Yalnızca Demo. `IS_DEMO=true` dışında hiçbir koşulda emir yok. Canlı hesap kapsam dışı.
- Manuel Demo emir ekranı yok (kaldırıldı). Emir yalnızca ajan akışından çıkar.
- Her ajanın kendi stratejisi var (`strategies.py`). Paper modu aynen kalır.
- Her emir G8 preflight'tan `AUTHORIZED` almadan borsaya gitmez (G8.6).

## 2. Kapılarla ilişki

G9 geçti (tek emir, durum doğrulama, iptal). Otomatik akış **G10–G16** kapsamındadır ve bu kapılar kanıtlanmadan açılmaz:

| Kapı | Bu tasarımda karşılığı |
|---|---|
| G10 Emir yaşam döngüsü | Bölüm 4.3 durum makinesi |
| G11 OrderSync | Bölüm 4.4 mutabakat |
| G12 Pozisyon bütünlüğü | Bölüm 4.5 ajan defteri |
| G13 Risk / kill switch | Bölüm 4.6 |
| G14 Yeniden başlatma | Bölüm 4.7 |
| G15 Hata enjeksiyonu | Bölüm 6 |
| G16 Demo soak | Bölüm 5, Faz D |

Varsayılan: `DEMO_AUTO_TRADING_ENABLED=false`. Açmak bilinçli, ayrı bir insan kararıdır.

## 3. Mimari

```
Strateji (strategies.py)  →  Intent {ajan, sembol, yön, neden, seq}
        →  DemoExecutor (tek kapı)
              1. risk ön kontrolü (4.6)
              2. G8 PreFlightValidator  → AUTHORIZED değilse DUR
              3. clOrdId üret (idempotent)
              4. borsaya gönder
        →  Yaşam döngüsü izleyici (4.3)  →  Ajan defteri (4.5)
        →  Mutabakat (4.4) her döngüde borsa ile karşılaştırır
```

**Tek kapı kuralı:** `create_order` çağrısı yalnızca `DemoExecutor` içinde olur. Testle zorunlu kılınır (başka modülde çağrı varsa test kırılır).

## 4. Bileşenler

### 4.1 Ajan modu
Her ajanın `mode` alanı: `paper` (varsayılan) veya `demo`. `demo`'ya geçiş: ajan pozisyonsuz olmalı, onay penceresi sembol, boyut ve limitleri göstermeli. `demo`'dan `paper`'a dönüş: açık emirler iptal, pozisyon kapalı olmalı.

### 4.2 Strateji → niyet
Strateji yalnızca **niyet** üretir; emir vermez. Aynı kenar (edge) sinyali ardışık tekrarlanırsa yeni niyet yok (mevcut `last_event_side` mantığı). Her niyetin ajan başına artan `seq` numarası olur.

### 4.3 Emir yaşam döngüsü (G10)
Durumlar: `NEW → SUBMITTED → ACKED → OPEN → PARTIAL → FILLED | CANCELED | REJECTED`, ek olarak `UNKNOWN`.

- `clOrdId = <ajan_kısa_id><seq>` (alfanümerik, ≤32). Aynı niyet iki kez gönderilemez.
- Gönderim zaman aşımına uğrarsa durum `UNKNOWN` olur; **yeniden gönderilmez**. `fetch_order` ile `clOrdId` üzerinden çözülür. Çözülemezse ajan durdurulur.
- Giriş emri: limit, fiyat koruması ile, **TTL 10 sn**; dolmazsa iptal edilir ve doğrulanır (G9'daki temizlik mantığı).
- Çıkış ve zarar durdurma: yalnızca küçültme (`reduceOnly`) emirleri.

### 4.4 Mutabakat (G11)
Her döngüde `fetch_open_orders` ve `fetch_positions` ile yerel kayıt karşılaştırılır. Fark varsa ilgili ajan durdurulur ve olay kaydı yazılır; bot tahminle düzeltme yapmaz. Bot etiketi (`clOrdId` öneki) olmayan emirlere dokunulmaz.

### 4.5 Ajan defteri ve pozisyon bütünlüğü (G12)
OKX'te bir enstrümandaki net pozisyon hesap genelindedir; birden fazla ajan aynı sembolde işlem yaparsa borsa bunları ayırmaz. Çözüm:

- Her ajan için **dahili defter** (dolumlar `clOrdId` ile ajana atfedilir).
- Değişmez kural: `Σ ajan pozisyonları == borsa pozisyonu` (her sembol için). Bozulursa tüm ilgili ajanlar durdurulur.
- **Faz B kısıtı:** sembol başına en fazla **bir** aktif Demo ajanı. Defter ancak Faz C'de çok ajanı destekler.

### 4.6 Risk ve kill switch (G13)
- Emir başına üst sınır: 1 kontrat (mevcut). Ajan başına en fazla pozisyon: başlangıçta 1 kontrat.
- Ajan başına günlük zarar limiti (öneri: Demo özsermayenin %2'si) → ajan durur, açık pozisyon kapatılır.
- Genel durdurma: `KILL_SWITCH_ACTIVE` ve dashboard'da görünür **"Tümünü durdur"** düğmesi (emirleri iptal eder, pozisyonları kapatır, ajanları `demo`'dan çıkarır).
- Devre kesici: dakikada en fazla N emir, art arda M borsa hatasında durdurma, bayat veri (`PF025`) durumunda niyet üretimi askıya alınır.
- Bot hesabın kaldıraç/marjin ayarını **değiştirmez**; ön koşul olarak elle ayarlanır, uyumsuzsa preflight (`PF027`) reddeder.

### 4.7 Yeniden başlatma (G14)
Defter ve son `seq` diske yazılır. Açılışta: durumu yükle → borsayla mutabakat → tüm Demo ajanları **`RECOVERED_PAUSED`** durumunda başlar, insan devam ettirir. Bot etiketli yetim emirler iptal edilir.

## 5. Teslim fazları

| Faz | İçerik | Borsaya emir | Kanıt |
|---|---|---|---|
| A — Gölge mod | Ajanlar Demo fiyatıyla niyet üretir, preflight çalışır, **hiçbir şey gönderilmez**; niyet günlüğü | Yok | Niyetler ve preflight sonuçları kayıtta |
| B — Tek ajan | Bir sembol, bir ajan, 1 kontrat, TTL'li limit; yaşam döngüsü + mutabakat | Var (kısıtlı) | G10, G11, G13 kanıtı |
| C — Çok ajan | Ajan defteri, sembol başına birden fazla ajan | Var | G12, G14 kanıtı |
| D — Soak | Uzun süreli Demo çalıştırma | Var | G15, G16 kanıtı |

Faz B'ye geçiş, Faz A'nın temiz günlüğü ve senin onayınla olur.

## 6. Test planı (G15 dahil)

Birim: durum makinesi geçişleri, `clOrdId` tekrarı reddi, `UNKNOWN` çözümü, defter değişmezi, günlük zarar limiti, kill switch.
Hata enjeksiyonu (sahte borsa): zaman aşımı, kısmi dolum, iptal reddi, bağlantı kopması, çift yanıt, bayat veri, borsa ile defter farkı, yeniden başlatma ortasında açık emir.
Statik: `create_order` yalnızca `DemoExecutor`'da; `IS_DEMO=false` iken hiçbir yol emir göndermez.

## 7. Çoklu kripto ile ilişki

Ajanın `sembol` alanı olacak; izinli liste (ör. BTC, ETH, SOL doğrusal swap'ları) ve her sembol için G8.1 metadata doğrulaması şarttır. Paper motoru şu an tek sembol varsayıyor; sembol bazlı yeniden yazım **Demo yürütücüsünden önce** yapılmalı, çünkü yürütücü sembolü girdi olarak alır.

## 8. Senin kararın gereken noktalar

1. Faz B'de sembol başına tek ajan kısıtı kabul mü?
2. Giriş için TTL'li limit, çıkış için küçültme emri yaklaşımı uygun mu?
3. Ajan başına günlük zarar limiti: %2 mi, başka bir değer mi?
4. Bir paper ajanını Demo'ya "terfi" ettirmek serbest mi, yoksa Demo ajanları baştan mı oluşturulsun?
