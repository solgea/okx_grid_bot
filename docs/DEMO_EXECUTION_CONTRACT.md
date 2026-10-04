# Demo Execution Sözleşmesi (G10–G16)

Durum: **v1.1, uygulamaya hazır; Faz A öncesi OKX varsayım doğrulaması gerekir**. Kaynak: `DEMO_AUTO_TRADING_DESIGN.md` (bu belge onun 8. bölümündeki kararları kilitler ve uygulanabilir sözleşmeye çevirir). Bu belge kod değildir; hiçbir emir yolunu açmaz.

## 0. Kilitli kararlar

| # | Karar |
|---|---|
| D1 | Faz B: sembol başına **tek** aktif Demo ajanı, en fazla 1 kontrat pozisyon, 1 kontrat emir. İhlal edilirse emir gönderilmez (sert değişmez). |
| D2 | Giriş: limit, TTL 10 sn, `reduceOnly=false`. Çıkış: `reduceOnly=true`. |
| D3 | Günlük zarar limiti %2, bölüm 6'daki tanımla. |
| D4 | Paper → Demo kontrollü terfi (bölüm 7). `seq` sıfırlanmaz. |
| D5 | Her faz geçişi için insan onayı gerekir (bölüm 10). |
| D6 | İkinci devre kesici: özsermaye düşüşü sert durdurma **%3**, gerçekleşmemiş K/Z dahil (bölüm 6). Günlük zarar limitinin alternatifi değil, ek bir katmandır. |
| D7 | Giriş fiyatı: LONG → en iyi satış (ask), SHORT → en iyi alış (bid); tick'e yuvarla; `abs(giriş − son) / son ≤ 0,002`. Spread aşırı genişse niyet düşer (`E_SPREAD`, `E_PRICE_BOUND`'dan ayrı). |
| D8 | `PROTECT_DEADLINE_SEC = 5`; süre emir gönderiminden değil **pozisyonun oluştuğunun tespit edildiği andan** başlar. |
| D9 | Faz A en az **3 ardışık gün** ve bölüm 10'daki tüm ölçütler birlikte sağlanmalı; süre tek başına PASS vermez. |

## 1. Değişmezler

Her değişmez bir testle korunur (bölüm 9). İhlal = emir yok / ajan durur.

| ID | Değişmez |
|---|---|
| I1 | `IS_DEMO != true` ise `create_order` **imkânsız**; yürütücü seviyesinde hata verir, yalnızca yapılandırma kontrolüne güvenilmez. |
| I2 | `create_order` yalnızca `OkxDemoTransport` içinde çağrılır; başka hiçbir modülde yoktur. Statik test tüm depoyu tarar. |
| I3 | `UNKNOWN` → `fetch_order` → çözüldüyse devam, çözülmediyse **ajan durur**. `UNKNOWN`'dan `create_order` tekrarı yoktur. |
| I4 | Yerel ≠ borsa ise ajan durur, olay kaydı yazılır, **otomatik düzeltme yoktur**. |
| I5 | Demo pozisyonu varken koruyucu çıkış (SL) doğrulanmış olmalı; doğrulanamıyorsa yeni giriş üretilmez (bölüm 5). |
| I6 | Niyet (`seq`) borsaya gitmeden **önce** diske yazılır (write-ahead). Aynı `(ajan, seq)` iki kez gönderilemez. |
| I7 | Korumasız pozisyon süresi `PROTECT_DEADLINE_SEC` (5 sn) ile sınırlıdır; süre `POSITION_DETECTED` anından başlar. Aşılırsa acil `reduceOnly` kapama ve ajan durur. |
| I8 | Faz kilidi: `DEMO_PHASE` değeri `A` iken borsaya giden taşıyıcı **oluşturulamaz** (bölüm 3). |

## 2. Modüller

Yeni paket `demo_exec/`. Mevcut `engine/`, `strategy/` ve G8 preflight'a dokunmaz; onları kullanır.

| Modül | Sorumluluk |
|---|---|
| `intent.py` | `Intent{agent_id, symbol, side, reason, seq, ts}`; ajan başına artan `seq`. |
| `journal.py` | Write-ahead günlük (JSONL, append-only, fsync). Niyet, durum geçişi ve olay kaydı. |
| `lifecycle.py` | Emir durum makinesi (bölüm 4). |
| `risk.py` | Sınırlar, günlük zarar, devre kesici (bölüm 6). |
| `executor.py` | Tek yürütme otoritesi; sözleşme bölüm 3. |
| `transport.py` | `Transport` arayüzü; `NullTransport` (Faz A) ve `OkxDemoTransport` (Faz B+). |
| `reconciler.py` | Borsa ile yerel durumu karşılaştırır (G11). |
| `promotion.py` | Terfi durum makinesi (bölüm 7). |
| `recovery.py` | Yeniden başlatma (G14). |

## 3. Yürütücü sözleşmesi

`DemoExecutor.submit(intent) -> SubmitResult` sırası **sabittir**; her adım başarısızsa dur ve neden kodu döndür.

| Adım | Kontrol | Başarısızlık kodu |
|---|---|---|
| 1 | `IS_DEMO` true, `DEMO_AUTO_TRADING_ENABLED` true | `E_NOT_DEMO`, `E_DISABLED` |
| 2 | Taşıyıcı gerçek mi? Faz A'da `NullTransport` zorunlu | `E_PHASE_LOCK` |
| 3 | Ajan modu `demo` ve durumu `RUNNING` | `E_AGENT_STATE` |
| 4 | D1 kısıtları: sembol başına tek ajan, pozisyon ve emir ≤ 1 kontrat | `E_LIMIT` |
| 5 | Risk ön kontrolü: günlük zarar, devre kesici, kill switch | `E_RISK`, `E_KILL` |
| 6 | G8 preflight; `AUTHORIZED` değilse dur. Giriş fiyatı ve spread kontrolü (D7) | `E_PREFLIGHT_<kod>`, `E_PRICE_BOUND`, `E_SPREAD` |
| 7 | Niyeti journal'a yaz (I6), `clOrdId` üret | `E_JOURNAL` |
| 8 | `transport.place(...)` | `E_TRANSPORT` → `UNKNOWN` |

`clOrdId = "g" + <ajan_kısa_id> + <seq>`; **harfle başlar**, yalnızca alfanümerik, ≤ 32 karakter (ajan kimliği rakamla başlayabildiği için `g` öneki zorunlu). Terfide `seq` korunur.

**Giriş fiyatı (D7):** LONG → en iyi satış, SHORT → en iyi alış; tick'e yuvarlanır; `abs(giriş − son) / son ≤ 0,002` aşılırsa `E_PRICE_BOUND`. Spread `MAX_SPREAD_PCT`'i aşarsa `E_SPREAD` (öneri: %0,1; değer onay bekliyor). İki neden ayrı kodlanır ki journal ve hata ayıklama ayrışsın.

## 4. Emir durum makinesi (G10)

```
NEW → SUBMITTED → ACKED → OPEN → PARTIAL → FILLED
                     │       │       └──────→ CANCELED (kalan iptal)
                     │       └─ TTL → CANCEL_SENT → CANCEL_CONFIRMED | FILLED (yarış)
                     └→ REJECTED
SUBMITTED/CANCEL_SENT zaman aşımı → UNKNOWN → (fetch_order) → çözüldü | ajan durur
```

| Olay | Kural |
|---|---|
| Gönderim zaman aşımı | `UNKNOWN`; `clOrdId` ile `fetch_order`; yeniden gönderme yok. |
| TTL doldu (10 sn) | `cancel` → `fetch_order` → `CANCEL_CONFIRMED`. |
| **İptal–dolum yarışı** | İptal reddi veya `filled > 0` ise dolum olarak işlenir (G9'daki `FILLED_POSITION_OPEN` mantığı). Dolum sonrası koruma kuralları başlar. |
| Kısmi dolum + TTL | Kalan iptal edilir, dolan miktar pozisyondur, koruma gerekir. |
| `REJECTED` | Ajan durmaz; neden journal'a yazılır; art arda M ret devre kesiciyi tetikler. |
| Borsa hatası | Hata sayacı artar; eşik aşılırsa ajan durur. |

## 5. Pozisyon koruması (I5, I7)

- `POSITION_DETECTED` = `fetch_order`/dolum akışında `filled > 0`'ın ya da mutabakatta pozisyon büyüklüğü değişiminin **ilk görüldüğü an**; journal'a yazılır. Emir açıkken yoklama aralığı ≤ 1 sn olmalıdır, böylece tespit gecikmesi deadline'a sayılmaz.
- **Tercih:** SL, giriş emrine bağlı (OKX `attachAlgoOrds`) gönderilir; koruma dolumla birlikte oluşur.
- Bağlı SL desteklenmezse: dolumdan sonra hemen `reduceOnly` SL, `PROTECT_DEADLINE_SEC` içinde onaylanmalı.
- SL onaylanmazsa: acil `reduceOnly` kapama → ajan `STOPPED`.
- Mutabakat (G11) SL emirlerini de listeler; pozisyon var, SL yoksa `INCIDENT` ve acil kapama.
- SL mesafesi, preflight'ta "SL'de en kötü kayıp ≤ günlük limit" şartıyla boyutlanır (bölüm 6).

## 6. Risk (G13)

**Günlük zarar:**

```
daily_loss = realized_pnl + trading_fees + funding      (gerçekleşmemiş K/Z hariç)
daily_loss <= -(0,02 × equity_snapshot)  →  AGENT_STOPPED
```

- `equity_snapshot`: her UTC gününün başında (ya da ajan aktivasyonunda) alınıp diske yazılan Demo özsermayesi. Gün içinde limit hesabın büyüklüğüyle değişmez.
- Durdurma sırası: açık emirleri iptal et → pozisyonu `reduceOnly` kapat → `AGENT_STOPPED`.
- **İkinci devre kesici (D6):** `(realized + unrealized + fees + funding) ≤ −%3 × equity_snapshot` olduğunda: açık emirleri iptal et → `reduceOnly` kapat → `STOPPED` → incident journal. **Otomatik yeniden başlatma yoktur**; devam yalnızca insan kararıyla. %2 limit gerçekleşmiş zararı, %3 hard-stop gerçekleşmemiş dahil toplam düşüşü izler.
- **Not 2:** 1 kontrat (≈ 0,01 ETH) için %2 limit pratikte nadiren tetiklenir; Faz B'de asıl bağlayıcı sınırlar emir/pozisyon üst sınırları ve SL'dir. Limit, Faz C'de boyut arttığında anlam kazanır.
- Diğer: dakikada en fazla N emir, art arda M hata, bayat veri (`PF025`) → niyet askıya, genel `KILL_SWITCH_ACTIVE`, dashboard "Tümünü durdur".
- Bot kaldıraç veya marjin ayarını değiştirmez (`PF027`).

## 7. Paper → Demo terfisi (D4)

```
PAPER → PROMOTION_PENDING → DEMO
```

`PROMOTION_PENDING`'den `DEMO`'ya geçiş için **hepsi** doğrulanmalı: ajan pozisyonsuz; açık emir yok; sembol izinli listede; G8.1 metadata geçerli; risk limitleri tanımlı; kaldıraç/marjin uyumlu; `IS_DEMO=true`; **insan onayı** (dashboard onay penceresi: sembol, boyut, limitler, `seq`). Biri başarısızsa `PAPER`'da kalır, neden gösterilir. Ajan kimliği, olay geçmişi ve `seq` korunur. Geri dönüş (`DEMO → PAPER`): emirler iptal, pozisyon kapalı şartıyla.

## 8. Mutabakat ve yeniden başlatma (G11, G14)

- Her döngü: `fetch_open_orders`, `fetch_positions`, açık algo/SL emirleri ↔ yerel kayıt. Fark → I4.
- Yalnızca bot etiketli (`clOrdId` önekli) emirlere dokunulur.
- Açılış: journal yüklenir → mutabakat → tüm Demo ajanları `RECOVERED_PAUSED`; insan devam ettirir. Yetim bot emirleri iptal edilir; pozisyon varsa SL doğrulanır.
- Journal bozuksa veya `seq` boşluğu varsa ajan başlamaz.

## 9. Test matrisi

| ID | Senaryo | Beklenen | Kapı |
|---|---|---|---|
| T01 | `IS_DEMO=false` ile submit | `E_NOT_DEMO`, taşıyıcı çağrılmaz | I1 |
| T02 | Depoda `create_order` aranır | Yalnızca `OkxDemoTransport` | I2 |
| T03 | `DEMO_PHASE=A` ile `OkxDemoTransport` kurulur | Hata | I8 |
| T04 | Preflight reddi | Emir yok | G8.6 |
| T05 | Aynı `(ajan, seq)` ikinci kez | `E_JOURNAL` | I6 |
| T06 | Journal yazımı sonrası çökme | `seq` yeniden kullanılmaz | I6, G14 |
| T07 | Gönderim zaman aşımı | `UNKNOWN`, tekrar gönderim yok | I3 |
| T08 | `UNKNOWN` çözülemez | Ajan durur | I3 |
| T09 | TTL → iptal onayı | `CANCEL_CONFIRMED` | G10 |
| T10 | TTL anında dolum (yarış) | Dolum olarak işlenir, koruma başlar | G10 |
| T11 | Kısmi dolum + TTL | Kalan iptal, dolan korunur | G10 |
| T12 | Ret | Journal'a neden; ajan durmaz | G10 |
| T13 | Çift/gecikmiş borsa yanıtı | Durum geri gitmez | G10 |
| T14 | Borsa ≠ yerel emir | Ajan durur, düzeltme yok | I4, G11 |
| T15 | Etiketsiz emir | Dokunulmaz | G11 |
| T16 | Pozisyon var, SL yok | Acil kapama | I5, I7 |
| T17 | SL onayı gecikir > deadline | Acil kapama | I7 |
| T18 | İkinci ajan aynı sembol | `E_LIMIT` | D1 |
| T19 | Günlük zarar ≤ −%2 | Emirler iptal, kapama, `STOPPED` | G13 |
| T20 | Snapshot gün içinde hesap büyüklüğüyle değişmez | Limit sabit | G13 |
| T21 | Devre kesici (hata, hız) | Ajan durur | G13 |
| T22 | Kill switch | Tüm emir/pozisyon temizlenir | G13 |
| T23 | Terfi: pozisyonlu / emirli / izinsiz sembol | `PAPER`'da kalır | D4 |
| T24 | Terfi sonrası `seq` | Devam eder, `clOrdId` çakışmaz | D4 |
| T25 | Açılışta açık emir/pozisyon | `RECOVERED_PAUSED` | G14 |
| T26 | Bozuk journal / `seq` boşluğu | Ajan başlamaz | G14 |
| T27 | Bağlantı kopması, çift yanıt, bayat veri enjeksiyonu | Güvenli duruş | G15 |

## 10. Fazlar ve onay kapıları

```
G9 PASS → Faz A → [G10/G11/G13 testleri PASS + İNSAN ONAYI] → Faz B
       → [G12/G14 PASS + İNSAN ONAYI] → Faz C → [G15 PASS] → Faz D → [G16 PASS]
```

**Faz A kabul ölçütü (gölge mod):** aşağıdakilerin **hepsi** (yalnızca süre yetmez):

```
3 ardışık gün
AND T01–T08 PASS  AND T14–T15 PASS  AND T23–T26 PASS
AND 0 beklenmeyen borsa-emir çağrısı   (NullTransport sayacı = 0 ve T02/T03 yeşil)
AND 0 çözülmemiş journal/mutabakat incident'ı
AND Bölüm 11'deki OKX doğrulama çıktısı repoda kayıtlı
```

Ayrıca: `DEMO_PHASE=A`, yalnızca `NullTransport`; niyetler ve preflight/ret kodları journal'da; niyet sayısı, ret dağılımı ve bayat veri olayları raporlanır. Faz A bitmeden **hiçbir gerçek Demo `create_order` yolu açılmaz**.

**Faz B kabul ölçütü:** Tek sembol, tek ajan, 1 kontrat. T09–T13, T16–T22 yeşil; en az N emirlik gerçek Demo çalıştırmasında her emir için `status`, `cleanup` ve mutabakat kanıtı; kayıtlı hiçbir `UNKNOWN`/`INCIDENT` çözümsüz değil. Onay kaydı repoda tutulur (`agent/APPROVALS.md`, tarih ve gerekçe).

## 11. OKX Demo varsayımları — doğrulama durumu

Salt-okuma betiği: `scripts/okx_demo_assumptions_check.py` (yalnızca `publicGet*` / `privateGet*`; tüm mutasyon yöntemleri çalışmadan önce engellenir). Çalıştırma:

```
docker compose -f docker-compose.g9.yml run --rm --entrypoint python okx-grid-bot-g9 scripts/okx_demo_assumptions_check.py
```

| # | Varsayım | Durum |
|---|---|---|
| 1 | Bağlı SL (`attachAlgoOrds`) ve algo emir listeleme | Belge düzeyinde: emir gönderiminde `attachAlgoOrds` ve `GET /trade/orders-algo-pending` var (ikincil kaynaklar: üçüncü taraf SDK'lar; OKX birincil belgesiyle teyit edilmeli). Listeleme sorgusu betikle okunur. **Demo'da bağlı SL desteği salt-okumayla kanıtlanamaz → Faz B ilk kontrollü çalıştırmada.** |
| 2 | Pozisyon modu, `reduceOnly` | `GET /account/config` `posMode` betikle okunur. `reduceOnly` alanı emirlerde mevcut; net modda davranışı **emir gerektirir → Faz B**. |
| 3 | Fee ve funding | Betik: işlem ücreti oranları, dolum kayıtlarında `fee`/`feeCcy` alanları, funding faturası (`type=8`) erişimi, funding oranı alanları. Henüz dolum/funding yoksa `NO_DATA` döner; alanlar ilk dolumdan sonra kanıtlanır. |
| 4 | `clOrdId` kuralları | Belge düzeyinde: 1–32 karakter, büyük/küçük harf duyarlı, alfanümerik; eski bir OKX rehberi harfle başlamayı şart koşuyor → **harfle başlama kuralı benimsendi** (bölüm 3). Aynı `clOrdId`'nin tekrar kullanımında borsa davranışı **doğrulanmadı → Faz B**; sözleşme zaten tekrar göndermeyi yasaklıyor (I6). |
| 5 | Parametreler | Karara bağlandı: %0,2 giriş sınırı, 5 sn deadline, Faz A 3 gün. `MAX_SPREAD_PCT` değeri açık. |

Betik çıktısı `UNVERIFIED_READ_ONLY` döndürdüğü maddeleri açıkça işaretler; bunlar Faz A kabulünü engellemez ama **Faz B girişinde ilk kontrollü çalıştırmanın kanıtı olarak zorunludur**.

## 12. Açık nokta

1. `MAX_SPREAD_PCT` değeri (öneri %0,1).
