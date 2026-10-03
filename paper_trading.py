"""Local-only paper trading for public OKX swap market data."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections import deque
from pathlib import Path
from typing import Any

logger = logging.getLogger("PaperTrading")

INSTRUMENT_ID = "ETH-USDT-SWAP"
CONTRACT_SIZE = 0.01
MAX_CONTRACTS = 100
MAX_LEVERAGE = 5
FEE_RATE = 0.0005
MAX_DRAWDOWN_PCT = 10.0


class PaperTradingError(ValueError):
    """An order or agent request cannot be safely executed."""


class PaperTradingManager:
    def __init__(self, state_path: str | Path = "data/paper_state.json") -> None:
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._market_thread: threading.Thread | None = None
        self._market_price: float | None = None
        self._market_updated_at: float | None = None
        self._market_error: str | None = None
        self._price_history: deque[float] = deque(maxlen=120)
        self._initial_balance = 10_000.0
        self._balance = self._initial_balance
        self._positions: dict[str, dict[str, float]] = {}
        self._agents: dict[str, dict[str, Any]] = {}
        self._fills: deque[dict[str, Any]] = deque(maxlen=100)
        self._load_state()

    def start_market_feed(self) -> None:
        with self._lock:
            if self._market_thread and self._market_thread.is_alive():
                return
            self._stop_event.clear()
            self._market_thread = threading.Thread(
                target=self._market_loop, name="okx-paper-market-feed", daemon=True
            )
            self._market_thread.start()

    def stop_market_feed(self) -> None:
        self._stop_event.set()
        thread = self._market_thread
        if thread and thread.is_alive():
            thread.join(timeout=6)

    def _market_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                price = self.fetch_public_price()
                self.on_price(price)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                with self._lock:
                    self._market_error = f"{type(exc).__name__}: {exc}"
                logger.warning("OKX public ticker unavailable: %s", exc)
            self._stop_event.wait(3)

    @staticmethod
    def fetch_public_price() -> float:
        query = urllib.parse.urlencode({"instId": INSTRUMENT_ID})
        request = urllib.request.Request(
            f"https://www.okx.com/api/v5/market/ticker?{query}",
            headers={"User-Agent": "OKX-Grid-Bot-Paper/1.0"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("code") != "0" or not payload.get("data"):
            raise ValueError(f"OKX ticker response was not successful: {payload.get('msg', 'unknown error')}")
        price = float(payload["data"][0]["last"])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("OKX returned an invalid ticker price")
        return price

    def on_price(self, price: float, timestamp: float | None = None) -> None:
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Market price must be a finite positive number")
        now = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._market_price = float(price)
            self._market_updated_at = now
            self._market_error = None
            self._price_history.append(float(price))
            for agent in list(self._agents.values()):
                self._update_agent(agent, float(price))
            self._save_state()

    def create_agent(
        self, name: str, contracts: int = 1, leverage: int = 2
    ) -> dict[str, Any]:
        clean_name = self._validate_name(name)
        self._validate_size(contracts)
        self._validate_leverage(leverage)
        with self._lock:
            if len(self._agents) >= 10:
                raise PaperTradingError("En fazla 10 paper trading ajanı oluşturulabilir.")
            agent = {
                "id": uuid.uuid4().hex[:12],
                "name": clean_name,
                "strategy": "EMA 9/21 kesişimi",
                "contracts": contracts,
                "leverage": leverage,
                "active": False,
                "signal": "Bekliyor",
                "fast_ema": self._market_price,
                "slow_ema": self._market_price,
                "previous_relation": "neutral" if self._market_price is not None else None,
                "realized_pnl": 0.0,
                "loss_limit_usdt": round(self._initial_balance * MAX_DRAWDOWN_PCT / 100, 2),
                "halt_reason": None,
            }
            self._agents[agent["id"]] = agent
            self._save_state()
            return self._public_agent(agent)

    def set_agent_active(self, agent_id: str, active: bool) -> dict[str, Any]:
        with self._lock:
            agent = self._get_agent(agent_id)
            if active and self._market_is_stale():
                raise PaperTradingError("OKX fiyat akışı güncel değil; ajan başlatılamadı.")
            agent["active"] = active
            agent["halt_reason"] = None
            agent["signal"] = "İzleniyor" if active else "Durduruldu"
            self._save_state()
            return self._public_agent(agent)

    def update_agent(
        self,
        agent_id: str,
        name: str | None = None,
        contracts: int | None = None,
        leverage: int | None = None,
    ) -> dict[str, Any]:
        """Edit an agent. Size/leverage may only change while the agent is flat."""
        if name is None and contracts is None and leverage is None:
            raise PaperTradingError("Güncellenecek alan belirtilmedi.")
        clean_name = self._validate_name(name) if name is not None else None
        if contracts is not None:
            self._validate_size(contracts)
        if leverage is not None:
            self._validate_leverage(leverage)
        with self._lock:
            agent = self._get_agent(agent_id)
            changes_risk = (contracts is not None and contracts != agent["contracts"]) or (
                leverage is not None and leverage != agent["leverage"]
            )
            if changes_risk and self._has_open_position(agent_id):
                raise PaperTradingError(
                    "Açık pozisyon varken kontrat veya kaldıraç değiştirilemez; önce pozisyonu kapatın."
                )
            if clean_name is not None:
                agent["name"] = clean_name
            if contracts is not None:
                agent["contracts"] = contracts
            if leverage is not None:
                agent["leverage"] = leverage
            self._save_state()
            return self._public_agent(agent)

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        """Remove an agent. Refused while it still holds an open position."""
        with self._lock:
            agent = self._get_agent(agent_id)
            if self._has_open_position(agent_id):
                raise PaperTradingError("Açık pozisyonu olan ajan silinemez; önce pozisyonu kapatın.")
            del self._agents[agent_id]
            self._positions.pop(agent_id, None)
            self._save_state()
            return self._public_agent(agent)

    def place_order(self, agent_id: str, side: str, contracts: int) -> dict[str, Any]:
        if side not in ("buy", "sell"):
            raise PaperTradingError("Yön buy veya sell olmalı.")
        self._validate_size(contracts)
        with self._lock:
            if self._market_is_stale() or self._market_price is None:
                raise PaperTradingError("OKX fiyatı henüz alınmadı veya güncel değil.")
            agent = self._get_agent(agent_id)
            return self._execute_order(
                agent, side, contracts, self._market_price, source="Manuel"
            )

    def close_position(self, agent_id: str) -> dict[str, Any] | None:
        with self._lock:
            agent = self._get_agent(agent_id)
            position = self._positions.get(agent_id)
            if not position or position["size"] == 0:
                return None
            if self._market_is_stale() or self._market_price is None:
                raise PaperTradingError("OKX fiyatı güncel değil; pozisyon kapatılamadı.")
            side = "sell" if position["size"] > 0 else "buy"
            contracts = round(abs(position["size"]) / CONTRACT_SIZE)
            return self._execute_order(
                agent, side, contracts, self._market_price, source="Pozisyon kapatma"
            )

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            age = (
                max(0.0, now - self._market_updated_at)
                if self._market_updated_at is not None
                else None
            )
            unrealized = sum(
                self._unrealized(position, self._market_price)
                for position in self._positions.values()
                if self._market_price is not None
            )
            equity = self._balance + unrealized
            margin_used = sum(
                abs(position["size"]) * self._market_price / position["leverage"]
                for position in self._positions.values()
                if self._market_price is not None
            )
            positions = []
            for agent_id, position in self._positions.items():
                agent = self._agents.get(agent_id)
                if not agent or position["size"] == 0:
                    continue
                positions.append(
                    {
                        "agent_id": agent_id,
                        "agent_name": agent["name"],
                        "side": "long" if position["size"] > 0 else "short",
                        "contracts": round(abs(position["size"]) / CONTRACT_SIZE, 4),
                        "entry_price": round(position["entry_price"], 4),
                        "mark_price": self._market_price,
                        "unrealized_pnl": round(
                            self._unrealized(position, self._market_price), 4
                        ),
                        "leverage": position["leverage"],
                    }
                )
            return {
                "mode": "paper",
                "exchange": "OKX public market data",
                "instrument": INSTRUMENT_ID,
                "contract_size": CONTRACT_SIZE,
                "price": self._market_price,
                "price_age_seconds": round(age, 1) if age is not None else None,
                "market_connected": age is not None and age <= 15,
                "market_error": self._market_error,
                "initial_balance": round(self._initial_balance, 2),
                "balance": round(self._balance, 2),
                "equity": round(equity, 2),
                "realized_pnl": round(self._balance - self._initial_balance, 2),
                "unrealized_pnl": round(unrealized, 2),
                "total_pnl": round(equity - self._initial_balance, 2),
                "available_margin": round(max(0.0, equity - margin_used), 2),
                "positions": positions,
                "agents": [self._public_agent(agent) for agent in self._agents.values()],
                "fills": list(self._fills),
                "price_history": list(self._price_history),
            }

    def _update_agent(self, agent: dict[str, Any], price: float) -> None:
        fast_alpha = 2 / (9 + 1)
        slow_alpha = 2 / (21 + 1)
        if agent["fast_ema"] is None:
            agent["fast_ema"] = price
            agent["slow_ema"] = price
            return
        previous = agent["previous_relation"]
        agent["fast_ema"] += fast_alpha * (price - agent["fast_ema"])
        agent["slow_ema"] += slow_alpha * (price - agent["slow_ema"])
        relation = (
            "long" if agent["fast_ema"] > agent["slow_ema"] else
            "short" if agent["fast_ema"] < agent["slow_ema"] else "neutral"
        )
        agent["previous_relation"] = relation
        if not agent["active"]:
            return
        agent["signal"] = "Alış sinyali" if relation == "long" else "Satış sinyali" if relation == "short" else "Nötr"
        if previous in ("long", "short") and relation in ("long", "short") and relation != previous:
            try:
                self._execute_order(
                    agent,
                    "buy" if relation == "long" else "sell",
                    agent["contracts"],
                    price,
                    source="EMA 9/21",
                )
            except PaperTradingError as exc:
                agent["active"] = False
                agent["halt_reason"] = str(exc)
                agent["signal"] = "Risk nedeniyle durduruldu"
                logger.warning("Agent %s stopped: %s", agent["id"], exc)
        position = self._positions.get(agent["id"])
        agent_pnl = agent["realized_pnl"] + (
            self._unrealized(position, price) if position else 0.0
        )
        if agent["active"] and agent_pnl <= -agent["loss_limit_usdt"]:
            if position:
                self._close_at_price(agent, position, price, "Zarar durdurma")
            agent["active"] = False
            agent["halt_reason"] = (
                f"{agent['loss_limit_usdt']:.2f} USDT ajan zarar limiti"
            )
            agent["signal"] = "Zarar limitiyle durduruldu"
        self._save_state()

    def _execute_order(
        self,
        agent: dict[str, Any],
        side: str,
        contracts: int,
        price: float,
        source: str,
    ) -> dict[str, Any]:
        size = contracts * CONTRACT_SIZE * (1 if side == "buy" else -1)
        old = self._positions.get(
            agent["id"], {"size": 0.0, "entry_price": 0.0, "leverage": agent["leverage"]}
        )
        previous_size = old["size"]
        closes_existing = previous_size != 0 and previous_size * size < 0
        closed_size = min(abs(previous_size), abs(size)) if closes_existing else 0.0
        opening_size = abs(size) - closed_size
        fee = abs(size) * price * FEE_RATE
        realized = (
            (price - old["entry_price"]) * closed_size * (1 if previous_size > 0 else -1)
            if closed_size
            else 0.0
        )

        remaining_size = previous_size + math.copysign(closed_size, size) if closed_size else previous_size
        if opening_size:
            remaining_size += math.copysign(opening_size, size)
        projected_position = (
            {"size": remaining_size, "entry_price": price if opening_size else old["entry_price"], "leverage": agent["leverage"]}
            if remaining_size
            else None
        )
        projected_equity = self._balance + realized - fee
        projected_margin = 0.0
        for existing_id, position in self._positions.items():
            candidate = projected_position if existing_id == agent["id"] else position
            if candidate:
                projected_equity += self._unrealized(candidate, price)
                projected_margin += abs(candidate["size"]) * price / candidate["leverage"]
        if agent["id"] not in self._positions and projected_position:
            projected_equity += self._unrealized(projected_position, price)
            projected_margin += abs(projected_position["size"]) * price / projected_position["leverage"]
        if opening_size and projected_equity - projected_margin < 0:
            raise PaperTradingError("Yetersiz kullanılabilir teminat; emir reddedildi.")

        self._balance += realized - fee
        agent["realized_pnl"] += realized - fee
        if projected_position:
            if opening_size and previous_size * size >= 0:
                total_size = abs(previous_size) + opening_size
                entry_price = (
                    old["entry_price"] * abs(previous_size) + price * opening_size
                ) / total_size
                projected_position["entry_price"] = entry_price
            self._positions[agent["id"]] = projected_position
        else:
            self._positions.pop(agent["id"], None)

        fill = {
            "id": uuid.uuid4().hex[:12],
            "time": time.time(),
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "side": side,
            "contracts": contracts,
            "price": round(price, 4),
            "notional": round(abs(size) * price, 4),
            "fee": round(fee, 4),
            "realized_pnl": round(realized - fee, 4),
            "source": source,
        }
        self._fills.appendleft(fill)
        self._save_state()
        return fill

    def _close_at_price(
        self, agent: dict[str, Any], position: dict[str, float], price: float, source: str
    ) -> None:
        side = "sell" if position["size"] > 0 else "buy"
        contracts = round(abs(position["size"]) / CONTRACT_SIZE)
        self._execute_order(agent, side, contracts, price, source)

    def _unrealized(
        self, position: dict[str, float], price: float | None
    ) -> float:
        if price is None:
            return 0.0
        direction = 1 if position["size"] > 0 else -1
        return (price - position["entry_price"]) * abs(position["size"]) * direction

    def _market_is_stale(self) -> bool:
        return (
            self._market_updated_at is None
            or time.time() - self._market_updated_at > 15
        )

    def _has_open_position(self, agent_id: str) -> bool:
        position = self._positions.get(agent_id)
        return bool(position and position["size"] != 0)

    @staticmethod
    def _validate_name(name: str) -> str:
        if not isinstance(name, str):
            raise PaperTradingError("Ajan adı metin olmalı.")
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 40:
            raise PaperTradingError("Ajan adı 1-40 karakter arasında olmalı.")
        return clean_name

    def _get_agent(self, agent_id: str) -> dict[str, Any]:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise PaperTradingError("Ajan bulunamadı.")
        return agent

    @staticmethod
    def _validate_size(contracts: int) -> None:
        if isinstance(contracts, bool) or not isinstance(contracts, int) or not 1 <= contracts <= MAX_CONTRACTS:
            raise PaperTradingError(f"Kontrat miktarı 1-{MAX_CONTRACTS} arasında tam sayı olmalı.")

    @staticmethod
    def _validate_leverage(leverage: int) -> None:
        if isinstance(leverage, bool) or not isinstance(leverage, int) or not 1 <= leverage <= MAX_LEVERAGE:
            raise PaperTradingError(f"Kaldıraç 1-{MAX_LEVERAGE}x arasında tam sayı olmalı.")

    @staticmethod
    def _public_agent(agent: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in agent.items()
            if key not in ("fast_ema", "slow_ema", "previous_relation")
        }

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._initial_balance = float(state["initial_balance"])
            self._balance = float(state["balance"])
            self._positions = state["positions"]
            self._agents = state["agents"]
            self._fills = deque(state["fills"], maxlen=100)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f"Paper trading state could not be loaded: {self.state_path}") from exc

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "initial_balance": self._initial_balance,
            "balance": self._balance,
            "positions": self._positions,
            "agents": self._agents,
            "fills": list(self._fills),
        }
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.state_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump(state, temporary_file, ensure_ascii=False)
            os.replace(temporary_path, self.state_path)
        except OSError:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise
