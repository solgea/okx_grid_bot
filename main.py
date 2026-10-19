"""Entry point for the OKX grid bot.

This module only wires the runtime components together. The trading cycle,
market consumption, kill switch, retry policy and trade journal live in the
``bot`` package so each concern can be tested and reviewed on its own.
"""

import asyncio
import logging
import signal
import sys
import time
from typing import Any

from adapters.okx_adapter import OKXPreFlightAdapter
from adapters.risk_adapter import RiskPreFlightAdapter
from bot.backoff import BackoffPolicy
from bot.kill_switch import KillSwitch, emergency_flatten_authorized
from bot.market_consumer import MarketConsumer
from bot.market_state import MarketState
from bot.trade_log import TradeLog
from bot.trading_loop import TradingLoop
from config.settings import config, to_native_symbol
from engine.exchange import OKXEngine
from engine.risk_manager import RiskManager
from engine.sync_engine import OrderSyncEngine
from preflight_layer.cache import load_state, save_state
from preflight_layer.order_manager import OrderManager
from preflight_layer.risk_policy import RiskPolicy
from preflight_layer.validator import PreFlightValidator
from strategy.grid_engine import GridEngine
from strategy.smc_engine import SMCVolumeEngine

# Loglama Ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s: %(message)s'
)
logger = logging.getLogger("MainLoop")

BOT_STATE_FILE = "bot_state.json"
RISK_STATE_FILE = "risk_state.json"

# Re-exported for callers that import the flatten rule from the entry point.
__all__ = ["build_components", "emergency_flatten_authorized", "main"]


def build_components() -> dict[str, Any]:
    """Construct the engines, adapters and strategy objects."""
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
    exchange_adapter = OKXPreFlightAdapter(engine)
    risk_adapter = RiskPreFlightAdapter(risk, policy=risk_policy)
    validator = PreFlightValidator(risk_manager=risk_adapter, policy=risk_policy)
    order_manager = OrderManager(adapter=exchange_adapter, validator=validator)
    sync = OrderSyncEngine(engine)
    return {
        "engine": engine,
        "risk": risk,
        "smc": smc,
        "grid": grid,
        "exchange_adapter": exchange_adapter,
        "order_manager": order_manager,
        "sync": sync,
    }


async def main():
    logger.info("🤖 Kurumsal Seviye Algoritmik Bot Başlatılıyor...")
    logger.info(f"Sembol: {config.SYMBOL} | Timeframe: {config.TIMEFRAME} | Kaldıraç: {config.LEVERAGE}x")

    components = build_components()
    engine = components["engine"]
    risk = components["risk"]
    smc = components["smc"]
    grid = components["grid"]
    exchange_adapter = components["exchange_adapter"]
    order_manager = components["order_manager"]
    sync = components["sync"]

    stop_event = asyncio.Event()
    stream_task = None
    market_state = MarketState()
    trade_log = TradeLog()

    try:
        await engine.initialize()
        instrument_metadata = await exchange_adapter.fetch_instrument_metadata(config.SYMBOL)
        restored_state = await load_state(BOT_STATE_FILE)
        if restored_state:
            grid.restore_state(restored_state.get("grid", {}))
            await market_state.restore_smc(restored_state.get("smc_data"))
            logger.info("💾 Grid FSM state cache'den geri yüklendi.")

        consumer = MarketConsumer(
            adapter=exchange_adapter,
            smc=smc,
            grid=grid,
            state=market_state,
        )

        loop = asyncio.get_running_loop()
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signal_name, stop_event.set)
            except (NotImplementedError, RuntimeError):
                pass
        stream_task = asyncio.create_task(
            consumer.run(to_native_symbol(config.SYMBOL), config.TIMEFRAME),
            name="okx-market-stream",
        )

        initial_account = await exchange_adapter.fetch_account_state()
        initial_balance = float(initial_account.balance)
        restored_risk_state = await load_state(RISK_STATE_FILE)
        if restored_risk_state:
            risk.restore_state(restored_risk_state, initial_balance)
            logger.info("💾 Risk state cache'den doğrulanarak geri yüklendi.")
        else:
            risk.initialize_balance(initial_balance)
            await save_state(RISK_STATE_FILE, risk.export_state())
            risk.mark_state_persisted()
        logger.info(f"💰 Başlangıç Cüzdan Bakiyesi Kaydedildi: {initial_balance:.2f} USDT")

        await trade_log.ensure_header()

        trading_loop = TradingLoop(
            engine=engine,
            exchange_adapter=exchange_adapter,
            order_manager=order_manager,
            sync=sync,
            risk=risk,
            grid=grid,
            state=market_state,
            trade_log=trade_log,
            kill_switch=KillSwitch(engine, config.SYMBOL),
            stop_event=stop_event,
            initial_balance=initial_balance,
            instrument_metadata=instrument_metadata,
            backoff=BackoffPolicy(),
        )
        await trading_loop.run()

    finally:
        stop_event.set()
        if stream_task:
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)
        await save_state(RISK_STATE_FILE, risk.export_state())
        risk.mark_state_persisted()
        await save_state(
            BOT_STATE_FILE,
            {
                "grid": grid.to_state(),
                "smc_data": await market_state.take_pending_smc(),
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
