import ccxt.async_support as ccxt
import asyncio
import logging
from config.settings import config

logger = logging.getLogger("OKXEngine")

class OKXEngine:
    def __init__(self):
        """
        OKX asenkron bağlantısını yapılandırır.
        Vadeli işlemler (futures/swap) için özel ayarları içerir.
        """
        exchange_config = {
            'apiKey': config.API_KEY,
            'secret': config.API_SECRET,
            'password': config.PASSPHRASE,
            'enableRateLimit': True, # API limitlerine takılmamak için otomatik bekleme
            'timeout': 30000,
            'options': {
                'defaultType': 'swap', # OKX Vadeli İşlemler (Perpetual Swap) için kritik ayar
            }
        }
        
        self.exchange = ccxt.okx(exchange_config)
        self._connection_lock = asyncio.Lock()
        self.connection_generation = 0
        self.connected = False
        
        # Testnet (Sandbox / Demo) kontrolü
        if config.IS_DEMO:
            self.exchange.set_sandbox_mode(True)
            logger.info("🛠️ OKX Sandbox (Demo/Testnet) modunda başlatıldı.")
        else:
            logger.warning("⚠️ DİKKAT: OKX CANLI AĞ (Mainnet) modunda başlatıldı!")

    async def initialize(self):
        """
        Piyasaları yükler, kaldıraç ve marjin modunu ayarlar.
        """
        try:
            logger.info("Piyasalar yükleniyor...")
            await self.exchange.load_markets()
            self.connected = True
            self.connection_generation += 1
            
            logger.info(f"{config.SYMBOL} için Kaldıraç ({config.LEVERAGE}x) ve Marjin Modu ({config.MARGIN_MODE}) ayarlanıyor...")
            try:
                # CCXT'ye OKX'in istediği lever parametresini ekstra (params) olarak veriyoruz
                await self.exchange.set_margin_mode(
                    config.MARGIN_MODE, 
                    config.SYMBOL, 
                    params={"lever": int(config.LEVERAGE)}
                )
                await self.exchange.set_leverage(int(config.LEVERAGE), config.SYMBOL)
                logger.info("✅ Kaldıraç ve Marjin ayarları başarıyla uygulandı.")
            except Exception as e:
                logger.error(f"Kaldıraç/Marjin ayarlanamadı (Borsada zaten ayarlı olabilir): {e}")
                
        except Exception as e:
            self.connected = False
            logger.error(f"❌ Başlatma hatası: {e}")
            raise e

    async def reconnect(self):
        """Reconnect the CCXT transport without allowing concurrent reconnects."""
        async with self._connection_lock:
            if self.connected:
                return
            logger.warning("🔄 OKX bağlantısı yenileniyor; emir mutabakatı bekletiliyor.")
            try:
                await self.exchange.close()
            except Exception as close_error:
                logger.debug("Eski OKX bağlantısı kapatılamadı: %s", close_error)
            self.exchange = ccxt.okx({
                "apiKey": config.API_KEY,
                "secret": config.API_SECRET,
                "password": config.PASSPHRASE,
                "enableRateLimit": True,
                "timeout": 30000,
                "options": {"defaultType": "swap"},
            })
            if config.IS_DEMO:
                self.exchange.set_sandbox_mode(True)
            await self.initialize()
            logger.info("✅ OKX bağlantısı yenilendi (generation=%s).", self.connection_generation)

    async def fetch_current_price(self, symbol=config.SYMBOL):
        """Belirtilen sembolün anlık fiyatını çeker."""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            logger.error(f"Fiyat çekilirken hata oluştu: {e}")
            self.connected = False
            raise

    async def fetch_balance(self):
        """Borsadaki güncel toplam USDT bakiyesini döner."""
        try:
            balance = await self.exchange.fetch_balance()
            # OKX USDT bakiyesini alır (free + used = total)
            return float(balance.get('USDT', {}).get('free', 0.0)) # Grid emirleri için daha güvenli
        except Exception as e:
            logger.error(f"Bakiye çekilirken hata oluştu: {e}")
            self.connected = False
            raise

    
    async def place_order(self, symbol, side, amount, price=None, order_type="limit", params=None):
        """
        Emir gönderme fonksiyonu. DRY_RUN aktifse borsaya emir gitmez.
        """
        if params is None:
            params = {}

        if config.DRY_RUN:
            order_info = f"[{side.upper()}] {amount} {symbol} @ {price if price else 'MARKET'} | Params: {params}"
            logger.info(f"🟢 [SİMÜLASYON - DRY_RUN] Emir gönderilmiş sayıldı: {order_info}")
            return {"status": "simulated", "side": side, "amount": amount, "price": price, "params": params}

        try:
            logger.info(f"🚀 Borsaya emir iletiliyor: {side.upper()} {amount} {symbol} @ {price} | Params: {params}")
            
            # CCXT fonksiyonlarına params argümanı eklendi
            if order_type == "limit":
                order = await self.exchange.create_limit_order(symbol, side, amount, price, params)
            else:
                # Market emirlerinde price None olarak geçer, parametreleri güvenli bir şekilde kwarg ile iletiyoruz
                order = await self.exchange.create_market_order(symbol, side, amount, params=params)
            
            logger.info(f"✅ Emir başarıyla iletildi! ID: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"❌ Emir gönderiminde hata: {e}")
            return None

    async def create_orders(self, symbol, orders):
        """Create up to OKX's batch limit in one private API request."""
        if not orders:
            return []
        if config.DRY_RUN:
            return [
                {"status": "simulated", "symbol": symbol, **order}
                for order in orders
            ]
        try:
            payload = [
                {
                    "symbol": symbol,
                    "type": "limit",
                    "side": order["side"],
                    "amount": float(order["amount"]),
                    "price": float(order["price"]),
                    "params": order.get("params", {}),
                }
                for order in orders
            ]
            result = await self.exchange.create_orders(payload)
            logger.info("✅ Toplu emir gönderildi: %s adet", len(orders))
            return result
        except Exception:
            self.connected = False
            logger.exception("Toplu emir gönderimi başarısız: %s adet", len(orders))
            raise

    async def cancel_orders(self, order_ids, symbol=config.SYMBOL):
        """Cancel an order-id batch without falling back to unsafe empty state."""
        if not order_ids:
            return []
        if config.DRY_RUN:
            return [{"id": order_id, "status": "simulated"} for order_id in order_ids]
        try:
            result = await self.exchange.cancel_orders(order_ids, symbol)
            logger.info("✅ Toplu emir iptali gönderildi: %s adet", len(order_ids))
            return result
        except Exception:
            self.connected = False
            logger.exception("Toplu emir iptali başarısız: %s adet", len(order_ids))
            raise

    async def fetch_open_orders(self, symbol=config.SYMBOL):
        """Borsadaki mevcut açık limit emirlerini çeker."""
        if config.DRY_RUN:
            return []
            
        try:
            orders = await self.exchange.fetch_open_orders(symbol)
            return orders
        except Exception as e:
            logger.error(f"Açık emirler çekilirken hata: {e}")
            self.connected = False
            raise

    async def cancel_order(self, order_id: str, symbol: str):
        """
        Belirtilen ID'ye sahip tekil açık emri iptal eder.
        Grid senkronizasyon motoru (OrderSyncEngine) tarafından kullanılır.
        """
        try:
            # CCXT'nin tekil emir iptal fonksiyonu
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"🗑️ Eski emir başarıyla iptal edildi (ID: {order_id})")  # self.logger -> logger yapıldı
            return True
        except Exception as e:
            logger.error(f"⚠️ Emir iptal edilirken hata (ID: {order_id}): {e}")  # self.logger -> logger yapıldı
            return False    

    async def cancel_all_orders(self, symbol: str):
        """
        Belirtilen semboldeki tüm açık emirleri tek bir API isteğiyle toplu olarak iptal eder.
        Kill-switch ve acil durum prosedürleri için optimize edilmiştir.
        """
        try:
            logger.warning(f"🧹 [{symbol}] Toplu emir iptal (Cancel All Orders) isteği gönderiliyor...") # self.logger -> logger yapıldı
            # CCXT'nin OKX için sunduğu dahili toplu iptal fonksiyonu
            await self.exchange.cancel_all_orders(symbol)
            logger.info(f"✅ [{symbol}] Tahtadaki tüm açık emirler başarıyla temizlendi.") # self.logger -> logger yapıldı
        except Exception as e:
            logger.error(f"⚠️ Toplu iptal sırasında kritik hata: {e}") # self.logger -> logger yapıldı

    async def fetch_position(self, symbol=config.SYMBOL):
        """
        Borsadaki aktif vadeli işlem pozisyonunu ve anlık PnL bilgisini çeker.
        """
        if config.DRY_RUN:
            return {"size": 0.0, "entryPrice": 0.0, "unrealizedPnl": 0.0}
            
        try:
            positions = await self.exchange.fetch_positions([symbol])
            
            for p in positions:
                if p['symbol'] == symbol:
                    # GÜVENLİ DÖNÜŞÜM: Eğer değer None gelirse, 'or 0.0' devreye girer.
                    size = float(p.get('contracts') or 0.0)
                    
                    if p.get('side') == 'short':
                        size = -abs(size)
                        
                    unrealized_pnl = float(p.get('unrealizedPnl') or 0.0)
                    entry_price = float(p.get('entryPrice') or 0.0)
                    
                    return {
                        "size": size,
                        "entryPrice": entry_price,
                        "unrealizedPnl": unrealized_pnl
                    }
                    
            return {"size": 0.0, "entryPrice": 0.0, "unrealizedPnl": 0.0}
            
        except Exception as e:
            logger.error(f"❌ Pozisyon bilgisi çekilirken hata: {e}")
            self.connected = False
            raise

    async def close_position_market(self, symbol=config.SYMBOL):
        """
        Mevcut açık pozisyonu piyasa fiyatından (Market Order) anında kapatır.
        """
        pos = await self.fetch_position(symbol)
        size = pos["size"]
        
        if size == 0:
            logger.info("Kapatılacak açık pozisyon bulunamadı.")
            return None

        # Pozisyon Long ise Sell, Short ise Buy yönünde kapatılır
        side = "sell" if size > 0 else "buy"
        amount = abs(size)
        
        logger.warning(f"🚨 POZİSYON PİYASA FİYATINDAN KAPATILIYOR: {side.upper()} {amount} {symbol}")
        
        # Risk motorunun güvenliği için reduceOnly kesinlikle eklenmeli
        params = {"reduceOnly": True}
        
        return await self.place_order(symbol, side, amount, order_type="market", params=params)
        

    async def close_connection(self):
        """Bağlantıyı güvenli bir şekilde kapatır ve TCP soketlerini temizler."""
        logger.info("Borsa bağlantısı kapatılıyor...")
        self.connected = False
        if self.exchange:
            await self.exchange.close()
            # Aiohttp'nin soketleri serbest bırakması için çok kısa bir süre tanıyoruz
            await asyncio.sleep(0.25)