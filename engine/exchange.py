import asyncio
import logging

import ccxt.async_support as ccxt

from config.settings import config

logger = logging.getLogger("OKXEngine")


class OKXEngine:
    def __init__(self):
        exchange_config = {
            "apiKey": config.API_KEY,
            "secret": config.API_SECRET,
            "password": config.PASSPHRASE,
            "enableRateLimit": True,
            "timeout": 30000,
            "options": {"defaultType": "swap"},
        }
        self.exchange = ccxt.okx(exchange_config)
        self._connection_lock = asyncio.Lock()
        self.connection_generation = 0
        self.connected = False

        if config.IS_DEMO:
            self.exchange.set_sandbox_mode(True)
            logger.info("OKX Demo/Sandbox mode enabled.")
        else:
            logger.warning("OKX MAINNET mode enabled.")

    async def initialize(self):
        """Initialize the exchange using read-only operations only.

        Startup must never mutate exchange/account state. Leverage, margin
        mode, position mode, orders and cancellations are runtime concerns.
        """
        try:
            await self.read_only_bootstrap()
        except Exception:
            self.connected = False
            logger.exception("OKX read-only initialization failed")
            raise

    async def read_only_bootstrap(self):
        """Verify Demo connectivity and authenticated account visibility.

        Only public/read-only API calls are permitted here:
        load_markets, fetch_ticker, fetch_balance, fetch_positions and
        fetch_open_orders. No trade or account-setting mutation is allowed.
        """
        if not config.IS_DEMO:
            raise RuntimeError(
                "Read-only bootstrap requires IS_DEMO=true; refusing non-Demo startup"
            )

        logger.info(
            "Starting OKX Demo read-only bootstrap | symbol=%s", config.SYMBOL
        )

        await self.exchange.load_markets()
        if config.SYMBOL not in self.exchange.markets:
            raise ValueError(f"Unknown OKX symbol: {config.SYMBOL}")

        ticker = await self.exchange.fetch_ticker(config.SYMBOL)
        if not ticker or ticker.get("last") is None:
            raise RuntimeError(f"OKX ticker unavailable for {config.SYMBOL}")

        # Private read-only calls verify API credentials without requiring
        # Trade permission.
        balance = await self.exchange.fetch_balance()
        await self.exchange.fetch_positions([config.SYMBOL])
        open_orders = await self.exchange.fetch_open_orders(config.SYMBOL)

        self.connected = True
        self.connection_generation += 1

        logger.info(
            "OKX Demo read-only bootstrap PASS | symbol=%s | open_orders=%d | "
            "balance_visible=%s | position_snapshot=read",
            config.SYMBOL,
            len(open_orders),
            bool(balance),
        )

    async def reconnect(self):
        async with self._connection_lock:
            if self.connected:
                return
            try:
                await self.exchange.close()
            except Exception:
                logger.debug("Previous OKX connection close failed", exc_info=True)
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

    async def fetch_current_price(self, symbol=None):
        symbol = symbol or config.SYMBOL
        try:
            return (await self.exchange.fetch_ticker(symbol))["last"]
        except Exception:
            self.connected = False
            raise

    async def fetch_balance(self):
        try:
            balance = await self.exchange.fetch_balance()
            return float(balance.get("USDT", {}).get("free", 0.0))
        except Exception:
            self.connected = False
            raise

    async def place_order(self, symbol, side, amount, price=None, order_type="limit", params=None):
        params = dict(params or {})
        if config.DRY_RUN:
            return {"status": "simulated", "side": side, "amount": amount, "price": price, "params": params}

        try:
            if order_type == "limit":
                order = await self.exchange.create_limit_order(symbol, side, amount, price, params)
            elif order_type == "market":
                order = await self.exchange.create_market_order(symbol, side, amount, params)
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            if not order or not order.get("id"):
                raise RuntimeError("Exchange returned an order without an id")
            return order
        except Exception:
            self.connected = False
            logger.exception("Order submission failed")
            raise

    async def create_orders(self, symbol, orders):
        if not orders:
            return []
        if config.DRY_RUN:
            return [{"status": "simulated", "symbol": symbol, **order} for order in orders]
        payload = []
        for order in orders:
            payload.append({
                "symbol": symbol,
                "type": "limit",
                "side": order["side"],
                "amount": float(order["amount"]),
                "price": float(order["price"]),
                "params": dict(order.get("params", {})),
            })
        try:
            result = await self.exchange.create_orders(payload)
            self.connected = True
            return result
        except Exception:
            self.connected = False
            logger.exception("Batch order submission failed")
            raise

    async def cancel_orders(self, order_ids, symbol=None):
        if not order_ids:
            return []
        symbol = symbol or config.SYMBOL
        if config.DRY_RUN:
            return [{"id": oid, "status": "simulated"} for oid in order_ids]
        try:
            return await self.exchange.cancel_orders(order_ids, symbol)
        except Exception:
            self.connected = False
            logger.exception("Batch cancellation failed")
            raise

    async def fetch_open_orders(self, symbol=None):
        symbol = symbol or config.SYMBOL
        # An empty order book is valid only when the exchange explicitly
        # confirms it. Network/disconnect errors must propagate so callers
        # never reconcile against a fabricated empty snapshot.
        try:
            return await self.exchange.fetch_open_orders(symbol)
        except Exception:
            self.connected = False
            raise

    async def cancel_order(self, order_id, symbol):
        if config.DRY_RUN:
            return True
        try:
            await self.exchange.cancel_order(order_id, symbol)
            return True
        except Exception:
            self.connected = False
            logger.exception("Order cancellation failed: %s", order_id)
            raise

    async def cancel_all_orders(self, symbol):
        if config.DRY_RUN:
            return True
        try:
            await self.exchange.cancel_all_orders(symbol)
            remaining = await self.exchange.fetch_open_orders(symbol)
            if remaining:
                raise RuntimeError(f"Cancel-all verification failed: {len(remaining)} orders remain")
            return True
        except Exception:
            self.connected = False
            logger.exception("Cancel-all failed or could not be verified")
            raise

    async def fetch_position(self, symbol=None):
        symbol = symbol or config.SYMBOL
        if config.DRY_RUN:
            return {"size": 0.0, "entryPrice": 0.0, "unrealizedPnl": 0.0}
        try:
            positions = await self.exchange.fetch_positions([symbol])
            for position in positions:
                if position.get("symbol") != symbol:
                    continue
                size = float(position.get("contracts") or 0.0)
                if position.get("side") == "short":
                    size = -abs(size)
                return {
                    "size": size,
                    "entryPrice": float(position.get("entryPrice") or 0.0),
                    "unrealizedPnl": float(position.get("unrealizedPnl") or 0.0),
                }
            return {"size": 0.0, "entryPrice": 0.0, "unrealizedPnl": 0.0}
        except Exception:
            self.connected = False
            raise

    async def close_position_market(self, symbol=None):
        symbol = symbol or config.SYMBOL
        pos = await self.fetch_position(symbol)
        size = pos["size"]
        if size == 0:
            return None
        side = "sell" if size > 0 else "buy"
        return await self.place_order(
            symbol, side, abs(size), order_type="market", params={"reduceOnly": True}
        )

    async def close_connection(self):
        self.connected = False
        if self.exchange:
            await self.exchange.close()
            await asyncio.sleep(0.25)
