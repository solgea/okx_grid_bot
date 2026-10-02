"""Explicitly confirmed OKX Demo-only manual swap trading."""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Callable

import ccxt

from config.settings import CCXT_SYMBOL, NATIVE_SYMBOL, config

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
    def configured(self) -> bool:
        return bool(config.API_KEY and config.API_SECRET and config.PASSPHRASE)

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
                balance_response = exchange.fetch_balance()
                positions_response = exchange.fetch_positions([CCXT_SYMBOL])
                orders_response = exchange.fetch_open_orders(CCXT_SYMBOL)
                balance = balance_response.get("USDT", {})
                positions = [
                    self._public_position(position)
                    for position in positions_response
                    if position.get("symbol") == CCXT_SYMBOL
                    and float(position.get("contracts") or 0) != 0
                ]
                orders = [
                    self._public_order(order)
                    for order in orders_response
                    if order.get("symbol") == CCXT_SYMBOL
                ]
                state = {
                    "mode": "demo",
                    "configured": True,
                    "connected": True,
                    "account": "OKX Demo",
                    "symbol": CCXT_SYMBOL,
                    "instrument": NATIVE_SYMBOL,
                    "balance": self._number(balance.get("free")),
                    "total_balance": self._number(balance.get("total")),
                    "positions": positions,
                    "open_orders": orders,
                    "error": None,
                    "refreshed_at": time.time(),
                }
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
            if not self.configured:
                raise DemoTradingError(
                    ".env içinde OKX Demo API bilgileri ayarlanmalı."
                )
            try:
                exchange = self._get_exchange()
                market = exchange.market(CCXT_SYMBOL)
                amount = float(exchange.amount_to_precision(CCXT_SYMBOL, contracts))
                minimum = market.get("limits", {}).get("amount", {}).get("min")
                if amount <= 0 or (minimum is not None and amount < float(minimum)):
                    raise DemoTradingError(
                        "Kontrat miktarı OKX en düşük işlem limitinin altında."
                    )
                formatted_price = (
                    float(exchange.price_to_precision(CCXT_SYMBOL, price))
                    if order_type == "limit" and price is not None
                    else None
                )
                exchange_order = exchange.create_order(
                    CCXT_SYMBOL,
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
                    "symbol": CCXT_SYMBOL,
                    "instrument": NATIVE_SYMBOL,
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
                    "OKX Demo order failed (%s).",
                    type(exc).__name__,
                )
                raise DemoTradingError(
                    f"OKX Demo emri gönderilemedi ({type(exc).__name__})."
                ) from None

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

    def _state_error(self, error: str) -> dict[str, Any]:
        return {
            "mode": "demo",
            "configured": self.configured,
            "connected": False,
            "account": "OKX Demo",
            "symbol": CCXT_SYMBOL,
            "instrument": NATIVE_SYMBOL,
            "balance": None,
            "total_balance": None,
            "positions": [],
            "open_orders": [],
            "error": error,
            "refreshed_at": None,
        }
