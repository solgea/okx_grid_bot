"""Kill-switch handling for the grid bot.

The kill switch is the last line of defense: it cancels every open order and,
only when explicitly authorized, flattens the open position. The decision to
flatten lives here so the trading loop stays readable and the authorization
rule has a single definition.
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import config

logger = logging.getLogger("KillSwitch")


def emergency_flatten_authorized(position_size: float) -> bool:
    """Return True only when a non-zero position may be flattened."""
    return (
        abs(position_size) > 0
        and config.EMERGENCY_FLATTEN_ENABLED
        and config.EMERGENCY_FLATTEN_AUTHORIZED
    )


class KillSwitch:
    """Applies the emergency protocol when a risk limit is breached."""

    def __init__(self, engine: Any, symbol: str) -> None:
        self.engine = engine
        self.symbol = symbol

    async def apply(self, position_size: float) -> None:
        """Cancel all orders and flatten the position when authorized.

        The caller must stop the trading loop after this returns.
        """
        logger.critical(
            "🛑 RİSK LİMİTİ AŞILDI! ACİL DURUM PROTOKOLÜ (KILL-SWITCH) AKTİF!"
        )
        try:
            await self.engine.cancel_all_orders(self.symbol)
            if emergency_flatten_authorized(position_size):
                await self.engine.close_position_market(self.symbol)
                logger.critical(
                    f"💥 [{self.symbol}] {position_size} büyüklüğündeki pozisyon "
                    "EMERGENCY_FLATTEN ile marketten KAPATILDI."
                )
            elif abs(position_size) > 0:
                logger.critical(
                    "⚠️ KILL_SWITCH yalnızca yeni emirleri durdurdu ve açık emirleri iptal etti; "
                    "EMERGENCY_FLATTEN ayrı yetkilendirilmedi."
                )
            else:
                logger.critical(
                    "ℹ️ Kapatılacak açık pozisyon bulunmuyor, emirler temizlendi."
                )
        except Exception as panic_error:
            logger.error(f"🚨 KILL-SWITCH UYGULANIRKEN HATA: {panic_error}")
        finally:
            logger.critical("⛔ Sistem güvenliğe alındı. İşlem döngüsü sonlandırılıyor.")
