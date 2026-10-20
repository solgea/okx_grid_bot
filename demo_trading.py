"""Explicitly confirmed OKX Demo-only manual swap trading."""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from decimal import Decimal
from typing import Any, Callable

import ccxt

from config.settings import config, to_native_symbol
from preflight_layer.domain import (
    AccountState,
    MarketData,
    OrderIntent,
    OrderSide,
    OrderType,
    PreFlightState,
)
from preflight_layer.exchange_data import (
    account_state_from_balance,
    instrument_metadata_from_market,
    market_data_from_ticker,
)
from preflight_layer.risk_policy import RiskPolicy
from preflight_layer.validator import PreFlightValidator

logger = logging.getLogger("OKXDemoTrading")

MAX_DEMO_ORDER_CONTRACTS = 1.0
SNAPSHOT_TTL_SECONDS = 5.0


class DemoTradingError(ValueError):
    """A Demo connection or order request is invalid or unavailable."""


class DemoTradingManager:
    def __init__(
        self, exchange_factory: Callable[..., Any] | None = None
    ) -> None:
        self._exchange_factory = exchange_factory or ccxt.okx
        self._exchange: Any | None = None
        self._lock = threading.RLock()
        self._last_state: dict[str, Any] | None = None
        self._last_state_at = 0.0
        self._last_error: str | None = None

    @property
    def symbol(self) -> str:
        """The configured unified symbol; the Demo panel follows SYMBOL."""
        return config.SYMBOL

    @property
    def native_symbol(self) -> str:
        """The native OKX instrument id for the configured symbol."""
        return to_native_symbol(config.SYMBOL)

    @property
    def configured(self) -> bool:
        return bool(config.API_KEY and config.API_SECRET and config.PASSPHRASE)

    @property
    def order_block_reason(self) -> str | None:
        """Why the panel cannot place a Demo order right now, if it cannot.

        Surfaced in the panel state so the operator sees the reason before
        attempting an order instead of only after it is rejected.
        """
        if not config.IS_DEMO:
            return "Demo modu kapalı; canlı emir gönderimi desteklenmez."
        if config.DRY_RUN:
            return (
                "DRY_RUN=true: simülasyon modundasınız, emir gönderilmez. "
                "Gerçek Demo emri için .env içinde DRY_RUN=false yapın."
            )
        if config.KILL_SWITCH_ACTIVE:
            return (
                "Kill switch açık: risk limiti aşıldı, emir gönderilmez. "
                "KILL_SWITCH_ACTIVE=false yaparak yeniden deneyebilirsiniz."
            )
        if not self.configured:
            return ".env içinde OKX Demo API bilgileri ayarlanmalı."
        return None

    def close(self) -> None:
        with self._lock:
            if self._exchange is not None:
                self._exchange.close()
                self._exchange = None
                self._last_state = None
                self._last_state_at = 0.0

    def get_state(self, force_refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if not config.IS_DEMO:
                return self._state_error(
                    "Demo modu kapalı. Canlı bağlantı bu panelden desteklenmez."
                )
            if not self.configured:
                return self._state_error(
                    ".env içinde API_KEY, API_SECRET ve PASSPHRASE ayarlanmalı."
                )
            if (
                not force_refresh
                and self._last_state is not None
                and time.monotonic() - self._last_state_at < SNAPSHOT_TTL_SECONDS
            ):
                return self._last_state
            try:
                exchange = self._get_exchange()
                symbol = self.symbol
                balance_response = exchange.fetch_balance()
                positions_response = exchange.fetch_positions([symbol])
                orders_response = exchange.fetch_open_orders(symbol)
                balance = balance_response.get("USDT", {})
                positions = [
                    self._public_position(position)
                    for position in positions_response
                    if position.get("symbol") == symbol
                    and float(position.get("contracts") or 0) != 0
                ]
                orders = [
                    self._public_order(order)
                    for order in orders_response
                    if order.get("symbol") == symbol
                ]
                state = self._state(
                    connected=True,
                    balance=self._number(balance.get("free")),
                    total_balance=self._number(balance.get("total")),
                    positions=positions,
                    open_orders=orders,
                    error=None,
                    refreshed_at=time.time(),
                )
                self._last_error = None
                self._last_state = state
                self._last_state_at = time.monotonic()
                return state
            except DemoTradingError as exc:
                self._last_error = str(exc)
                logger.warning("OKX Demo connection unavailable: %s", exc)
                return self._state_error(str(exc))
            except Exception as exc:
                self._last_error = f"OKX Demo bağlantı hatası ({type(exc).__name__})."
                logger.warning(
                    "OKX Demo private request failed (%s).",
                    type(exc).__name__,
                )
                return self._state_error(self._last_error)

    def place_order(
        self,
        side: str,
        order_type: str,
        contracts: float,
        price: float | None,
        confirm: bool,
    ) -> dict[str, Any]:
        """Place one confirmed Demo order after the same PreFlight gate the bot uses.

        The order only reaches the OKX Demo sandbox when every PreFlight
        check passes, exactly like the grid bot's execution path. A
        DRY_RUN configuration refuses the order instead of silently
        submitting it, so the demo panel cannot be used to bypass the
        simulation switch.
        """
        if confirm is not True:
            raise DemoTradingError("Emir için açık Demo onayı gerekli.")
        if side not in ("buy", "sell"):
            raise DemoTradingError("Yön buy veya sell olmalı.")
        if order_type not in ("limit", "market"):
            raise DemoTradingError("Emir türü limit veya market olmalı.")
        if isinstance(contracts, bool) or not isinstance(contracts, (int, float)):
            raise DemoTradingError("Kontrat miktarı sayısal olmalı.")
        if not math.isfinite(contracts) or contracts <= 0:
            raise DemoTradingError("Kontrat miktarı sıfırdan büyük ve geçerli olmalı.")
        if contracts > MAX_DEMO_ORDER_CONTRACTS:
            raise DemoTradingError(
                f"Demo emirleri en fazla {MAX_DEMO_ORDER_CONTRACTS:g} kontrat olabilir."
            )
        if order_type == "limit":
            if (
                isinstance(price, bool)
                or not isinstance(price, (int, float))
                or not math.isfinite(price)
                or price <= 0
            ):
                raise DemoTradingError("Limit emri için geçerli bir fiyat girilmeli.")
        else:
            price = None
        with self._lock:
            if not config.IS_DEMO:
                raise DemoTradingError(
                    "Demo modu kapalı; canlı emir gönderimi desteklenmez."
                )
            if config.DRY_RUN:
                raise DemoTradingError(
                    "DRY_RUN=true iken Demo emri gönderilmez. "
                    "Simülasyon modunda kalın veya DRY_RUN=false ile açıkça "
                    "Demo emir gönderimini etkinleştirin."
                )
            if not self.configured:
                raise DemoTradingError(
                    ".env içinde OKX Demo API bilgileri ayarlanmalı."
                )
            # The global kill switch is not bypassed here. When it is on,
            # PreFlight rejects the order with PF029 and nothing reaches the
            # exchange. The panel must not be a way around the bot's stop
            # control.
            try:
                exchange = self._get_exchange()
                symbol = self.symbol
                market = exchange.market(symbol)
                amount = float(exchange.amount_to_precision(symbol, contracts))
                minimum = market.get("limits", {}).get("amount", {}).get("min")
                if amount <= 0 or (minimum is not None and amount < float(minimum)):
                    raise DemoTradingError(
                        "Kontrat miktarı OKX en düşük işlem limitinin altında."
                    )
                formatted_price = (
                    float(exchange.price_to_precision(symbol, price))
                    if order_type == "limit" and price is not None
                    else None
                )

                metadata = instrument_metadata_from_market(symbol, market)
                account_state = self._account_state(exchange)
                market_state = self._market_state(exchange, symbol)

                intent = OrderIntent(
                    instrument_id=symbol,
                    side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                    order_type=OrderType.LIMIT if order_type == "limit" else OrderType.MARKET,
                    price=Decimal(str(formatted_price if formatted_price is not None else market_state.last)),
                    size=Decimal(str(amount)),
                    leverage=account_state.leverage,
                    margin_mode=config.MARGIN_MODE,
                    position_side="net",
                    reduce_only=False,
                    client_order_id=f"demo_{uuid.uuid4().hex[:16]}",
                )

                validator = PreFlightValidator(policy=self._policy())
                result = validator.validate(intent, metadata, account_state, market_state)
                if not result.passed or validator.state is not PreFlightState.AUTHORIZED:
                    raise DemoTradingError(
                        f"PreFlight reddi ({result.rejection_code}): {result.message}"
                    )

                exchange_order = exchange.create_order(
                    symbol,
                    order_type,
                    side,
                    amount,
                    formatted_price,
                    {"tdMode": "cross"},
                )
                self._last_state = None
                self._last_state_at = 0.0
                return {
                    "mode": "demo",
                    "id": str(exchange_order.get("id", "")),
                    "symbol": symbol,
                    "instrument": self.native_symbol,
                    "type": order_type,
                    "side": side,
                    "amount": self._number(exchange_order.get("amount") or amount),
                    "price": self._number(exchange_order.get("price") or formatted_price),
                    "status": str(exchange_order.get("status", "submitted")),
                    "timestamp": exchange_order.get("timestamp") or int(time.time() * 1000),
                }
            except DemoTradingError:
                raise
            except Exception as exc:
                logger.warning(
                    "OKX Demo order failed (%s): %s",
                    type(exc).__name__,
                    exc,
                )
                raise DemoTradingError(
                    f"OKX Demo emri gönderilemedi ({type(exc).__name__})."
                ) from None

    def _account_state(self, exchange: Any) -> AccountState:
        """Build the PreFlight account state from the Demo balance."""
        balance = exchange.fetch_balance()
        return account_state_from_balance(balance, Decimal(str(config.LEVERAGE)))

    def _market_state(self, exchange: Any, symbol: str) -> MarketData:
        """Build the PreFlight market state from the live Demo ticker."""
        ticker = exchange.fetch_ticker(symbol)
        return market_data_from_ticker(ticker, fallback_timestamp=time.time())

    def _policy(self) -> RiskPolicy:
        """Risk policy for the manual Demo panel.

        The panel places one explicitly confirmed order at a time, so its
        position ceiling is the panel's own one-contract cap rather than the
        bot's much smaller grid limit. Every other PreFlight gate
        (tick/lot alignment, minimum size, margin, market freshness) is
        unchanged.
        """
        return RiskPolicy(
            max_position_size=MAX_DEMO_ORDER_CONTRACTS,
            max_drawdown_pct=float(config.MAX_DRAWDOWN_PCT),
            max_daily_loss_usdt=float(config.MAX_DAILY_LOSS_USDT),
            market_data_max_age_sec=float(config.MARKET_DATA_MAX_AGE_SEC),
            max_leverage=float(config.LEVERAGE),
        )

    def _get_exchange(self) -> Any:
        if self._exchange is not None:
            return self._exchange
        if not self.configured:
            raise DemoTradingError(".env içinde OKX Demo API bilgileri ayarlanmalı.")
        exchange = self._exchange_factory(
            {
                "apiKey": config.API_KEY,
                "secret": config.API_SECRET,
                "password": config.PASSPHRASE,
                "enableRateLimit": True,
                "timeout": 10000,
                "options": {"defaultType": "swap"},
            }
        )
        exchange.set_sandbox_mode(True)
        exchange.load_markets()
        if not exchange.has.get("fetchPositions"):
            raise DemoTradingError("OKX Demo pozisyon okuma desteği bulunamadı.")
        self._exchange = exchange
        return exchange

    @classmethod
    def _public_position(cls, position: dict[str, Any]) -> dict[str, Any]:
        return {
            "side": str(position.get("side") or ""),
            "contracts": cls._number(position.get("contracts")),
            "entry_price": cls._number(position.get("entryPrice")),
            "mark_price": cls._number(position.get("markPrice")),
            "unrealized_pnl": cls._number(position.get("unrealizedPnl")),
            "leverage": cls._number(position.get("leverage")),
        }

    @classmethod
    def _public_order(cls, order: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(order.get("id") or ""),
            "side": str(order.get("side") or ""),
            "type": str(order.get("type") or ""),
            "amount": cls._number(order.get("amount")),
            "price": cls._number(order.get("price")),
            "status": str(order.get("status") or ""),
        }

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _state(
        self,
        *,
        connected: bool,
        balance: float | None = None,
        total_balance: float | None = None,
        positions: list[dict[str, Any]] | None = None,
        open_orders: list[dict[str, Any]] | None = None,
        error: str | None = None,
        refreshed_at: float | None = None,
    ) -> dict[str, Any]:
        """Build a Demo panel state payload.

        Single source of truth for the payload shape so the connected and
        disconnected states cannot drift apart.
        """
        return {
            "mode": "demo",
            "configured": self.configured,
            "connected": connected,
            "account": "OKX Demo",
            "symbol": self.symbol,
            "instrument": self.native_symbol,
            "balance": balance,
            "total_balance": total_balance,
            "positions": positions or [],
            "open_orders": open_orders or [],
            "error": error,
            "refreshed_at": refreshed_at,
            "order_block_reason": self.order_block_reason,
        }

    def _state_error(self, error: str) -> dict[str, Any]:
        return self._state(connected=False, error=error)
