import asyncio
import logging
import pandas_ta_classic as ta
import sys
import os
import aiofiles
import time
import signal
from collections import deque
from decimal import Decimal
from datetime import datetime

# CCXT Hata Sınıfları (Backoff Mekanizması İçin)
from ccxt.base.errors import RateLimitExceeded, RequestTimeout, NetworkError, ExchangeError

# Yapılandırma
from config.settings import config

# --- PREFLIGHT & ADAPTER IMPORTLARI ---
from preflight_layer.validator import PreFlightValidator
from preflight_layer.risk_policy import RiskPolicy
from preflight_layer.order_manager import OrderManager
from adapters.okx_adapter import OKXPreFlightAdapter
from adapters.risk_adapter import RiskPreFlightAdapter

# Motorlar ve Modüller
from engine.exchange import OKXEngine
from strategy.grid_engine import GridEngine
from strategy.smc_engine import SMCVolumeEngine
from preflight_layer.domain import MarketData
from engine.risk_manager import RiskManager
from engine.sync_engine import OrderSyncEngine
from adapters.market_stream import MarketEvent
from preflight_layer.cache import load_state, save_state

# Loglama Ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s: %(message)s'
)
logger = logging.getLogger("MainLoop")

async def write_csv_async(log_file: str, row_data: list):
    """Event loop'u kitlemeden dosyaya asenkron satır ekler."""
    line = ",".join(map(str, row_data)) + "\n"
    async with aiofiles.open(log_file, mode='a', newline='') as file:
        await file.write(line)

async def main():
    logger.info("🤖 Kurumsal Seviye Algoritmik Bot Başlatılıyor...")
    logger.info(f"Sembol: {config.SYMBOL} | Timeframe: {config.TIMEFRAME} | Kaldıraç: {config.LEVERAGE}x")
    
    # 1. Çekirdek (Core) Motorların Başlatılması
    engine = OKXEngine()
    risk_policy = RiskPolicy.from_config()
    risk = RiskManager(policy=risk_policy)
    smc = SMCVolumeEngine()
    grid = GridEngine(
        lower_price=config.LOWER_PRICE,
        upper_price=config.UPPER_PRICE,
        grid_count=config.GRID_COUNT,
        contract_size=config.CONTRACT_SIZE,
        price_precision=getattr(config, 'PRICE_PRECISION', 2),
        min_step_pct=getattr(config, 'MIN_STEP_PCT', 0.0020),
        tp_margin_pct=getattr(config, 'TP_MARGIN_PCT', 0.0025)
    )

    # 2. PreFlight (Uçuş Öncesi) Adaptörlerinin Kurulumu
    exchange_adapter = OKXPreFlightAdapter(engine)
    risk_adapter = RiskPreFlightAdapter(risk, policy=risk_policy)
    
    # 3. Validator ve Order Manager'ın Bağlanması
    validator = PreFlightValidator(risk_manager=risk_adapter, policy=risk_policy)
    order_manager = OrderManager(adapter=exchange_adapter, validator=validator)
    
    # 4. Senkronizasyon Motoru
    sync = OrderSyncEngine(engine)
    stop_event = asyncio.Event()
    stream_task = None
    latest_market = {"price": None, "smc_data": None, "confluence_score": None}

    try:
        await engine.initialize()
        instrument_metadata = await exchange_adapter.fetch_instrument_metadata(config.SYMBOL)
        restored_state = await load_state("bot_state.json")
        if restored_state:
            grid.restore_state(restored_state.get("grid", {}))
            latest_market["smc_data"] = restored_state.get("smc_data")
            logger.info("💾 Grid FSM state cache'den geri yüklendi.")

        async def consume_market_events():
            candles = deque(maxlen=100)
            async for event in exchange_adapter.market_events(
                config.SYMBOL.replace("/", "-").replace(":USDT", "-SWAP"),
                config.TIMEFRAME,
            ):
                try:
                    latest_market["price"] = event.price
                    if event.ohlcv and event.confirmed:
                        candles.append(event.ohlcv)
                        df = ta.DataFrame(
                            list(candles),
                            columns=["timestamp", "open", "high", "low", "close", "volume"],
                        )
                        if len(df) >= 3:
                            latest_market["smc_data"] = {
                                "volume_profile": smc.analyze_volume_profile(df),
                                "order_blocks": smc.identify_order_blocks(df),
                                **smc.analyze_structure(df),
                            }
                            confluence = smc.calculate_confluence(
                                df,
                                latest_market["smc_data"],
                                latest_market["smc_data"]["volume_profile"],
                            )
                            latest_market["smc_data"]["confluence_score"] = confluence.score
                            latest_market["confluence_score"] = confluence.score
                            smc.confluence_pool.release(confluence)
                            grid.update_grid_from_smc(
                                latest_market["smc_data"], event.price
                            )
                finally:
                    if event:
                        event_pool = exchange_adapter.market_stream.pool
                        if event_pool:
                            event_pool.release(event)

        loop = asyncio.get_running_loop()
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signal_name, stop_event.set)
            except (NotImplementedError, RuntimeError):
                pass
        stream_task = asyncio.create_task(consume_market_events(), name="okx-market-stream")
        
        initial_account = await exchange_adapter.fetch_account_state()
        initial_balance = float(initial_account.balance)
        restored_risk_state = await load_state("risk_state.json")
        if restored_risk_state:
            risk.restore_state(restored_risk_state, initial_balance)
            logger.info("💾 Risk state cache'den doğrulanarak geri yüklendi.")
        else:
            risk.initialize_balance(initial_balance)
            await save_state("risk_state.json", risk.export_state())
            risk.mark_state_persisted()
        logger.info(f"💰 Başlangıç Cüzdan Bakiyesi Kaydedildi: {initial_balance:.2f} USDT")
        
        log_file = "trade_execution_log.csv"
        if not os.path.exists(log_file):
            headers = ["Timestamp", "Symbol", "Action", "Position_Size", "Entry_Price", "Realized_PnL", "Unrealized_PnL", "Net_Total_PnL", "Wallet_Balance"]
            await write_csv_async(log_file, headers)
                
        last_position_size = 0.0
        last_realized_pnl = 0.0

        logger.info("🔄 Canlı İşlem ve Analiz Döngüsü Başlatıldı. (Çıkış için Ctrl+C)")

        retry_count = 0
        base_delay = 2       
        max_delay = 60       
        backoff_factor = 2   
        
        while not stop_event.is_set():
            try:
                current_price = latest_market["price"]
                if not current_price:
                    await asyncio.sleep(0.25)
                    continue

                logger.info(f"📈 [{config.SYMBOL}] Anlık Fiyat: {current_price:.2f} USDT")
                
                if latest_market["smc_data"] is not None:
                    grid.update_grid_from_smc(latest_market["smc_data"], current_price)
                    latest_market["smc_data"] = None

                position_data = await engine.fetch_position(config.SYMBOL)
                current_position_size = position_data.get("size", 0.0)
                unrealized_pnl = position_data.get("unrealizedPnl", 0.0)
                entry_price = position_data.get("entryPrice", 0.0)

                current_account = await exchange_adapter.fetch_account_state()
                current_wallet_balance = float(current_account.balance)

                realized_pnl = current_wallet_balance - initial_balance
                total_pnl = realized_pnl + unrealized_pnl
                pnl_percentage = (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0.0

                pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
                logger.info(
                    f"{pnl_icon} PnL: Gerçekleşen: {realized_pnl:+.2f} | Açık: {unrealized_pnl:+.2f} | "
                    f"Net: {total_pnl:+.2f} USDT (%{pnl_percentage:+.2f})"
                )

                position_changed = current_position_size != last_position_size
                pnl_changed_significantly = abs(realized_pnl - last_realized_pnl) > 0.05

                if position_changed or pnl_changed_significantly:
                    if abs(current_position_size) > abs(last_position_size):
                        action = "ENTRY / ADD"
                    elif abs(current_position_size) < abs(last_position_size):
                        action = "TAKE_PROFIT / REDUCE"
                    else:
                        action = "POSITION_UPDATE"

                    log_row = [
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        config.SYMBOL,
                        action,
                        current_position_size,
                        round(entry_price, 4) if entry_price else 0.0,
                        round(realized_pnl, 4),
                        round(unrealized_pnl, 4),
                        round(total_pnl, 4),
                        round(current_wallet_balance, 4)
                    ]
                    
                    await write_csv_async(log_file, log_row)
                    logger.info(f"📝 İşlem veritabanına kaydedildi -> {action}")
                    
                    last_position_size = current_position_size
                    last_realized_pnl = realized_pnl

                # --- KILL-SWITCH (ACİL DURUM RİSK MOTORU) ---
                if risk.check_risk_limits(current_wallet_balance + unrealized_pnl, abs(current_position_size)):
                    logger.critical("🛑 RİSK LİMİTİ AŞILDI! ACİL DURUM PROTOKOLÜ (KILL-SWITCH) AKTİF!")
                    try:
                        await engine.cancel_all_orders(config.SYMBOL)
                        if (
                            abs(current_position_size) > 0
                            and config.EMERGENCY_FLATTEN_ENABLED
                            and config.EMERGENCY_FLATTEN_AUTHORIZED
                        ):
                            await engine.close_position_market(config.SYMBOL)
                            logger.critical(
                                f"💥 [{config.SYMBOL}] {current_position_size} büyüklüğündeki pozisyon "
                                "EMERGENCY_FLATTEN ile marketten KAPATILDI."
                            )
                        elif abs(current_position_size) > 0:
                            logger.critical(
                                "⚠️ KILL_SWITCH yalnızca yeni emirleri durdurdu ve açık emirleri iptal etti; "
                                "EMERGENCY_FLATTEN ayrı yetkilendirilmedi."
                            )
                        else:
                            logger.critical("ℹ️ Kapatılacak açık pozisyon bulunmuyor, emirler temizlendi.")
                    except Exception as panic_err:
                        logger.error(f"🚨 KILL-SWITCH UYGULANIRKEN HATA: {panic_err}")
                    finally:
                        logger.critical("⛔ Sistem güvenliğe alındı. İşlem döngüsü sonlandırılıyor.")
                        break

                if risk.state_dirty:
                    await save_state("risk_state.json", risk.export_state())
                    risk.mark_state_persisted()

                # --- POZİSYON LİMİT KONTROLÜ (SOFT-LIMIT BARIYERİ) ---
                # Pozisyon büyüklüğü azami kontrat/büyüklük sınırına ulaştıysa yeni giriş emri açılmasını engelliyoruz.
                max_pos_limit = getattr(config, 'MAX_POSITION_SIZE', getattr(config, 'MAX_POS_SIZE', None))
                
                is_limit_breached = False
                if max_pos_limit is not None and abs(current_position_size) >= max_pos_limit:
                    is_limit_breached = True
                else:
                    position_limit_checker = getattr(risk, 'is_position_limit_reached', None)
                    if callable(position_limit_checker):
                        is_limit_breached = position_limit_checker(abs(current_position_size))

                # --- PREFLIGHT DESTEKLİ EMİR SENKRONİZASYONU ---
                target_orders = grid.get_target_orders(
                    current_price=current_price,
                    current_position_size=current_position_size,
                    entry_price=entry_price,
                    confluence_score=latest_market["confluence_score"],
                )

                open_orders_snapshot = await engine.fetch_open_orders(config.SYMBOL)
                current_account.current_position_size = Decimal(str(current_position_size))
                current_account.open_order_exposure = sum(
                    (abs(Decimal(str(order.get("amount") or 0))) for order in open_orders_snapshot),
                    Decimal("0"),
                )

                preflight_account = current_account
                preflight_market = MarketData(
                    bid=Decimal(str(current_price)),
                    ask=Decimal(str(current_price)),
                    last=Decimal(str(current_price)),
                    timestamp=time.time(),
                )
                target_orders, execution_authorization = order_manager.authorize_intents(
                    target_orders,
                    instrument_metadata,
                    preflight_account,
                    preflight_market,
                )
                
                # Execution boundary requires the exact PreFlight authorization token.
                await sync.sync_orders(
                    target_orders,
                    authorization=execution_authorization,
                    is_limit_breached=is_limit_breached,
                )

                if retry_count > 0:
                    logger.info("✅ API bağlantısı normale döndü. Gecikme sayacı sıfırlandı.")
                    retry_count = 0

                await asyncio.sleep(2)

            except (RateLimitExceeded, RequestTimeout) as api_err:
                retry_count += 1
                sleep_time = min(max_delay, base_delay * (backoff_factor ** retry_count))
                logger.warning(f"⚠️ Borsa Limiti veya Zaman Aşımı: {type(api_err).__name__}. {sleep_time} saniye bekleniyor... (Deneme: {retry_count})")
                if isinstance(api_err, RequestTimeout):
                    try:
                        await engine.reconnect()
                    except Exception as reconnect_error:
                        logger.error(f"🔁 Yeniden bağlanma başarısız: {reconnect_error}")
                await asyncio.sleep(sleep_time)

            except NetworkError as net_err:
                retry_count += 1
                sleep_time = min(max_delay, base_delay * (backoff_factor ** retry_count))
                logger.error(f"🔌 Ağ Bağlantı Hatası. {sleep_time} saniye bekleniyor... (Deneme: {retry_count})")
                try:
                    await engine.reconnect()
                except Exception as reconnect_error:
                    logger.error(f"🔁 Yeniden bağlanma başarısız: {reconnect_error}")
                await asyncio.sleep(sleep_time)

            except ExchangeError as exchange_err:
                retry_count += 1
                logger.error("OKX exchange error: %s", exchange_err)
                if not engine.connected:
                    try:
                        await engine.reconnect()
                    except Exception as reconnect_error:
                        logger.error("Exchange reconnect failed: %s", reconnect_error)
                await asyncio.sleep(min(max_delay, base_delay * (backoff_factor ** retry_count)))

            except Exception as loop_err:
                logger.critical("Fatal internal execution error; halting: %s", loop_err, exc_info=True)
                break

    finally:
        stop_event.set()
        if stream_task:
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)
        await save_state("risk_state.json", risk.export_state())
        risk.mark_state_persisted()
        await save_state(
            "bot_state.json",
            {
                "grid": grid.to_state(),
                "smc_data": latest_market["smc_data"],
                "saved_at": time.time(),
            },
        )
        logger.info("🛑 Bot kapatılıyor, açık bağlantılar temizleniyor...")
        await engine.close_connection()
        logger.info("👋 Sistem güvenli bir şekilde kapatıldı.")

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        logging.getLogger("asyncio").setLevel(logging.CRITICAL)
        logging.getLogger("ccxt.base.exchange").setLevel(logging.CRITICAL)