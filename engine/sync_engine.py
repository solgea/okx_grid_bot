import asyncio
import logging
import re
from decimal import Decimal
from typing import Optional
from config.settings import config
from strategy.order_reconciler import OrderReconciler, GridOrderSpec, ExistingOrder

logger = logging.getLogger("OrderSyncEngine")

def _sanitize_cl_ord_id(cl_ord_id: Optional[str]) -> Optional[str]:
    """
    OKX API kurallarına göre clOrdId temizleyici.
    - Sadece alfabetik (a-z, A-Z) ve nümerik (0-9) karakterler.
    - Maksimum 32 karakter uzunluk.
    """
    if not cl_ord_id:
        return None
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', str(cl_ord_id))
    return cleaned[:32] if cleaned else None

class OrderSyncEngine:
    def __init__(self, exchange_engine):
        self.engine = exchange_engine
        self._sync_lock = asyncio.Lock()
        
        # İdeal senaryoda bu değerler exchange_engine üzerinden fetch_markets() ile
        # dinamik olarak paritenin tick_size ve lot_size değerlerine eşitlenmelidir.
        self.reconciler = OrderReconciler(
            price_tolerance=Decimal("0.00000001"),
            size_tolerance=Decimal("0.00000001")
        )

    async def sync_orders(self, target_intents, is_limit_breached: bool = False):
        """
        main.py'den gelen hedef emir niyetlerini borsadaki durumla eşitler.
        is_limit_breached=True gelirse, yeni giriş (entry) emirlerini hedeflerden çıkarır.
        """
        async with self._sync_lock:
            await self._sync_orders_locked(target_intents, is_limit_breached)

    async def _sync_orders_locked(self, target_intents, is_limit_breached: bool = False):
        try:
            # 1. Never reconcile against an invented empty snapshot after disconnect.
            raw_open_orders = await self.engine.fetch_open_orders(config.SYMBOL)
            
            # 2. CCXT formatını -> Reconciler'ın ExistingOrder formatına dönüştür
            open_orders = []
            for o in raw_open_orders:
                open_orders.append(ExistingOrder(
                    ord_id=o['id'],
                    price=Decimal(str(o['price'])),
                    size=Decimal(str(o['amount'])),
                    side=o['side'].lower(),
                    pos_side=o.get('info', {}).get('posSide', 'net').lower(),
                    cl_ord_id=_sanitize_cl_ord_id(o.get('clientOrderId'))
                ))

            # 3. Target Intent'leri -> Reconciler'ın GridOrderSpec formatına dönüştür
            target_orders = []
            for t in target_intents:
                side_str = t.side.value.lower()
                pos_side_str = t.position_side.lower()

                # --- RİSK BARKİYERİ: Emir türünü tespit et (Entry mi TP mi?) ---
                is_entry = False
                
                # Hedged mod (Long/Short) kontrolü
                if pos_side_str == "long" and side_str == "buy":
                    is_entry = True
                elif pos_side_str == "short" and side_str == "sell":
                    is_entry = True
                # One-way (Net) mod kontrolü
                elif pos_side_str in ["net", ""]:
                    # Intent objesinde reduce_only bayrağı varsa kontrol et, yoksa Buy'ları giriş varsay
                    if getattr(t, "reduce_only", False) == False and side_str == "buy":
                        is_entry = True

                # LİMİT AŞILDIYSA VE BU BİR GİRİŞ EMRİ YSE, HEDEFLERE EKLEME! (Filtrele)
                if is_limit_breached and is_entry:
                    continue 
                # -------------------------------------------------------------

                target_orders.append(GridOrderSpec(
                    price=Decimal(str(t.price)),
                    size=Decimal(str(t.size)),
                    side=side_str,
                    pos_side=pos_side_str,
                    cl_ord_id=_sanitize_cl_ord_id(t.client_order_id)
                ))

            if is_limit_breached:
                logger.warning(f"⚠️ Pozisyon Limiti Aktif! Giriş emirleri filtrelendi. Sadece {len(target_orders)} adet Kar-Al (TP) hedefi işlenecek.")

            # 4. Mutabakat Planını Çalıştır
            plan = self.reconciler.reconcile(target_orders, open_orders)

            if not plan.has_changes:
                return  # Değişiklik yoksa API'yi yormadan çık

            # --- ASENKRON UYGULAMA ADIMLARI ---
            
            # ADIM 1: İptaller (Reconciler filtrelediğimiz giriş emirlerini otomatik iptal edecek!)
            if plan.to_cancel_ids:
                logger.info(f"🗑️ İptal edilecek emirler: {len(plan.to_cancel_ids)} adet")
                await self._cancel_orders_async(plan.to_cancel_ids)

            # ADIM 2: Amend (Güncelleme - Geri Dönüşüm)
            if plan.to_amend_orders:
                logger.info(f"♻️ Güncellenecek (Amend) emirler: {len(plan.to_amend_orders)} adet")
                await self._amend_orders_async(plan.to_amend_orders)

            # ADIM 3: Yeni Emirler
            if plan.to_place_orders:
                logger.info(f"🆕 Yeni açılacak emirler: {len(plan.to_place_orders)} adet")
                await self._place_orders_async(plan.to_place_orders)

        except Exception as e:
            logger.error(f"🚨 Emir senkronizasyonu sırasında hata: {e}")
            raise # Hatanın main.py'deki Backoff mekanizmasına düşmesi için fırlatıyoruz

    async def _cancel_orders_async(self, order_ids):
        """Cancel the reconciliation delta through one batch call."""
        try:
            await self.engine.cancel_orders(order_ids, config.SYMBOL)
        except Exception as e:
            logger.error(f"Toplu iptal hatası: {e}")
            raise

    async def _amend_single_order(self, spec):
        """Tek bir emri günceller ve 51503, 51008, 51004 hatalarını sönümler."""
        params = {}
        sanitized_new_id = _sanitize_cl_ord_id(spec.new_cl_ord_id)
        if sanitized_new_id:
            params['newClOrdId'] = sanitized_new_id

        try:
            return await self.engine.exchange.edit_order(
                id=spec.ord_id,
                symbol=config.SYMBOL,
                type='limit',
                side=None,
                amount=float(spec.new_size),
                price=float(spec.new_price),
                params=params
            )
        except Exception as e:
            err_str = str(e)
            
            # Race Condition (Emir doldu/iptal oldu)
            if "51503" in err_str or "already been filled or canceled" in err_str.lower():
                logger.info(f"ℹ️ Emir [{spec.ord_id}] borsa tarafında zaten gerçekleşti/iptal edildi (Code 51503). Amend atlandı.")
                return None
                
            # Yetersiz Bakiye veya Yetersiz Margin (Grid boyutu artarsa Amend patlayabilir)
            if any(code in err_str for code in ["51008", "51004", "Insufficient"]):
                logger.warning(f"⚠️ Yetersiz Margin/Bakiye (Amend). Emir [{spec.ord_id}] güncellenemedi! Hata: {e}")
                return None
                
            logger.error(f"Amend işlemi başarısız (ID: {spec.ord_id}): {e}")
            return None

    async def _amend_orders_async(self, amend_specs):
        """
        Güncellenecek emirleri asenkron olarak borsaya iletir.
        OKX Rate limitlerini (60 istek / 2 sn) korumak için 20'şerli chunk'lar halinde işler.
        """
        chunk_size = 20
        for i in range(0, len(amend_specs), chunk_size):
            chunk = amend_specs[i:i + chunk_size]
            tasks = [self._amend_single_order(spec) for spec in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Eğer son chunk değilsek, spam engellemek için çok kısa bir bekleme
            if i + chunk_size < len(amend_specs):
                await asyncio.sleep(0.1)

    async def _place_single_order(self, spec):
        """Tek bir emri iletir ve Yetersiz Bakiye/Margin hatalarını sönümler."""
        params = {'posSide': spec.pos_side}
        sanitized_id = _sanitize_cl_ord_id(spec.cl_ord_id)
        if sanitized_id:
            params['clientOrderId'] = sanitized_id
            
        try:
            return await self.engine.exchange.create_order(
                symbol=config.SYMBOL,
                type='limit',
                side=spec.side,
                amount=float(spec.size),
                price=float(spec.price),
                params=params
            )
        except Exception as e:
            err_str = str(e)
            
            # 51008: Yetersiz Bakiye, 51004: Yetersiz Margin
            if any(code in err_str for code in ["51008", "51004", "Insufficient"]):
                logger.warning(f"⚠️ Yetersiz Margin/Bakiye (Place). {spec.side.upper()} {spec.size} @ {spec.price} emri açılamadı! (Kod: 51008/51004)")
                return None
                
            logger.error(f"Yeni emir iletimi başarısız: {e}")
            return None

    async def _place_orders_async(self, place_specs):
        """Yeni emirleri batch endpoint'iyle 20'şerli paketler halinde iletir."""
        chunk_size = 20
        for i in range(0, len(place_specs), chunk_size):
            chunk = place_specs[i:i + chunk_size]
            orders = [
                {
                    "side": spec.side,
                    "amount": spec.size,
                    "price": spec.price,
                    "params": self._order_params(spec),
                }
                for spec in chunk
            ]
            await self.engine.create_orders(config.SYMBOL, orders)
            
            # Eğer son chunk değilsek, spam engellemek için çok kısa bir bekleme
            if i + chunk_size < len(place_specs):
                await asyncio.sleep(0.1)

    @staticmethod
    def _order_params(spec):
        params = {"posSide": spec.pos_side}
        sanitized_id = _sanitize_cl_ord_id(spec.cl_ord_id)
        if sanitized_id:
            params["clientOrderId"] = sanitized_id
        return params