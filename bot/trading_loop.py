"""The trading cycle for the grid bot.

One iteration of this loop reconciles the grid's target orders against the
exchange. Every step that can place, amend or cancel an order is behind the
PreFlight authorization token; the loop never mutates exchange state
directly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

from ccxt.base.errors import ExchangeError, NetworkError, RateLimitExceeded, RequestTimeout

from bot.backoff import BackoffPolicy
from bot.kill_switch import KillSwitch
from bot.market_state import MarketState
from bot.trade_log import PNL_CHANGE_THRESHOLD, TradeLog
from config.settings import config
from preflight_layer.cache import save_state
from preflight_layer.domain import MarketData
from strategy.grid_engine import GridEngine

logger = logging.getLogger("TradingLoop")

POLL_INTERVAL_SECONDS = 2
NO_PRICE_POLL_SECONDS = 0.25


class TradingLoop:
    """Runs the order reconciliation cycle until the bot is stopped."""

    def __init__(
        self,
        *,
        engine: Any,
        exchange_adapter: Any,
        order_manager: Any,
        sync: Any,
        risk: Any,
        grid: GridEngine,
        state: MarketState,
        trade_log: TradeLog,
        kill_switch: KillSwitch,
        stop_event: asyncio.Event,
        initial_balance: float,
        backoff: BackoffPolicy | None = None,
    ) -> None:
        self.engine = engine
        self.exchange_adapter = exchange_adapter
        self.order_manager = order_manager
        self.sync = sync
        self.risk = risk
        self.grid = grid
        self.state = state
        self.trade_log = trade_log
        self.kill_switch = kill_switch
        self.stop_event = stop_event
        self.initial_balance = initial_balance
        self.backoff = backoff or BackoffPolicy()
        self.last_position_size = 0.0
        self.last_realized_pnl = 0.0

    async def run(self) -> None:
        """Run the cycle until the stop event is set."""
        logger.info("🔄 Canlı İşlem ve Analiz Döngüsü Başlatıldı. (Çıkış için Ctrl+C)")
        retry_count = 0

        while not self.stop_event.is_set():
            try:
                await self._cycle()
                if retry_count > 0:
                    logger.info("✅ API bağlantısı normale döndü. Gecikme sayacı sıfırlandı.")
                    retry_count = 0
            except (RateLimitExceeded, RequestTimeout) as api_error:
                retry_count += 1
                sleep_time = self.backoff.delay_for(retry_count)
                logger.warning(
                    "⚠️ Borsa Limiti veya Zaman Aşımı: %s. %s saniye bekleniyor... (Deneme: %s)",
                    type(api_error).__name__,
                    sleep_time,
                    retry_count,
                )
                if isinstance(api_error, RequestTimeout):
                    await self._reconnect()
                await asyncio.sleep(sleep_time)
            except NetworkError:
                retry_count += 1
                sleep_time = self.backoff.delay_for(retry_count)
                logger.error(
                    "🔌 Ağ Bağlantı Hatası. %s saniye bekleniyor... (Deneme: %s)",
                    sleep_time,
                    retry_count,
                )
                await self._reconnect()
                await asyncio.sleep(sleep_time)
            except ExchangeError as exchange_error:
                retry_count += 1
                logger.error("OKX exchange error: %s", exchange_error)
                if not self.engine.connected:
                    await self._reconnect()
                await asyncio.sleep(self.backoff.delay_for(retry_count))
            except Exception as loop_error:
                logger.critical(
                    "Fatal internal execution error; halting: %s", loop_error, exc_info=True
                )
                break

    async def _reconnect(self) -> None:
        """Reconnect to the exchange, logging any failure."""
        try:
            await self.engine.reconnect()
        except Exception as reconnect_error:
            logger.error("🔁 Yeniden bağlanma başarısız: %s", reconnect_error)

    async def _cycle(self) -> None:
        """Run one reconciliation cycle."""
        current_price = self.state.price
        if not current_price:
            await asyncio.sleep(NO_PRICE_POLL_SECONDS)
            return

        logger.info(f"📈 [{config.SYMBOL}] Anlık Fiyat: {current_price:.2f} USDT")

        await self._apply_pending_smc(current_price)

        position_data = await self.engine.fetch_position(config.SYMBOL)
        current_position_size = position_data.get("size", 0.0)
        unrealized_pnl = position_data.get("unrealizedPnl", 0.0)
        entry_price = position_data.get("entryPrice", 0.0)

        current_account = await self.exchange_adapter.fetch_account_state()
        current_wallet_balance = float(current_account.balance)

        realized_pnl = current_wallet_balance - self.initial_balance
        total_pnl = realized_pnl + unrealized_pnl
        pnl_percentage = (
            (total_pnl / self.initial_balance) * 100 if self.initial_balance > 0 else 0.0
        )

        pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
        logger.info(
            f"{pnl_icon} PnL: Gerçekleşen: {realized_pnl:+.2f} | Açık: {unrealized_pnl:+.2f} | "
            f"Net: {total_pnl:+.2f} USDT (%{pnl_percentage:+.2f})"
        )

        await self._journal_if_changed(
            current_position_size=current_position_size,
            entry_price=entry_price,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            wallet_balance=current_wallet_balance,
        )

        if self.risk.check_risk_limits(
            current_wallet_balance + unrealized_pnl, abs(current_position_size)
        ):
            await self.kill_switch.apply(current_position_size)
            self.stop_event.set()
            return

        if self.risk.state_dirty:
            await self._persist_risk_state()

        is_limit_breached = self._position_limit_breached(current_position_size)

        await self._reconcile(
            current_price=current_price,
            current_position_size=current_position_size,
            entry_price=entry_price,
            is_limit_breached=is_limit_breached,
            current_account=current_account,
        )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _apply_pending_smc(self, current_price: float) -> None:
        """Apply the newest SMC analysis to the grid, exactly once."""
        smc_data = await self.state.take_pending_smc()
        if smc_data is not None:
            self.grid.update_grid_from_smc(smc_data, current_price)

    async def _journal_if_changed(
        self,
        *,
        current_position_size: float,
        entry_price: float,
        realized_pnl: float,
        unrealized_pnl: float,
        total_pnl: float,
        wallet_balance: float,
    ) -> None:
        """Append a journal row when the position or PnL changed."""
        position_changed = current_position_size != self.last_position_size
        pnl_changed = abs(realized_pnl - self.last_realized_pnl) > PNL_CHANGE_THRESHOLD
        if not (position_changed or pnl_changed):
            return

        action = self.trade_log.classify_action(
            current_position_size, self.last_position_size
        )
        await self.trade_log.record(
            symbol=config.SYMBOL,
            action=action,
            position_size=current_position_size,
            entry_price=entry_price,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            wallet_balance=wallet_balance,
        )
        logger.info(f"📝 İşlem veritabanına kaydedildi -> {action}")

        self.last_position_size = current_position_size
        self.last_realized_pnl = realized_pnl

    def _position_limit_breached(self, current_position_size: float) -> bool:
        """Return True when the soft position limit is reached."""
        max_position_limit = getattr(
            config, "MAX_POSITION_SIZE", getattr(config, "MAX_POS_SIZE", None)
        )
        if max_position_limit is not None and abs(current_position_size) >= max_position_limit:
            return True
        position_limit_checker = getattr(self.risk, "is_position_limit_reached", None)
        if callable(position_limit_checker):
            return bool(position_limit_checker(abs(current_position_size)))
        return False

    async def _persist_risk_state(self) -> None:
        """Write the risk state and mark it as persisted."""
        await save_state("risk_state.json", self.risk.export_state())
        self.risk.mark_state_persisted()

    async def _reconcile(
        self,
        *,
        current_price: float,
        current_position_size: float,
        entry_price: float,
        is_limit_breached: bool,
        current_account: Any,
        instrument_metadata: Any,
    ) -> None:
        """Authorize the target orders and hand them to the sync engine."""
        target_orders = self.grid.get_target_orders(
            current_price=current_price,
            current_position_size=current_position_size,
            entry_price=entry_price,
            confluence_score=self.state.confluence_score,
        )

        open_orders_snapshot = await self.engine.fetch_open_orders(config.SYMBOL)
        current_account.current_position_size = Decimal(str(current_position_size))
        current_account.open_order_exposure = sum(
            (abs(Decimal(str(order.get("amount") or 0))) for order in open_orders_snapshot),
            Decimal("0"),
        )

        preflight_market = MarketData(
            bid=Decimal(str(current_price)),
            ask=Decimal(str(current_price)),
            last=Decimal(str(current_price)),
            timestamp=time.time(),
        )
        target_orders, execution_authorization = self.order_manager.authorize_intents(
            target_orders,
            instrument_metadata,
            current_account,
            preflight_market,
        )

        # Execution boundary requires the exact PreFlight authorization token.
        await self.sync.sync_orders(
            target_orders,
            authorization=execution_authorization,
            is_limit_breached=is_limit_breached,
        )
