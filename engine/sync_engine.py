"""Exchange order reconciliation orchestration for the grid bot."""
from __future__ import annotations
import asyncio
import logging
import re
import hashlib
from collections.abc import Iterable
from decimal import Decimal
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum
from config.settings import config
from strategy.order_reconciler import ExistingOrder, GridOrderSpec, OrderReconciler
from preflight_layer.domain import ExecutionAuthorization

logger = logging.getLogger("OrderSyncEngine")
_BATCH_SIZE = 20
_BATCH_DELAY_SECONDS = 0.1
_PRICE_TOLERANCE = Decimal("0.00000001")
_SIZE_TOLERANCE = Decimal("0.00000001")
_FILLED_OR_CANCELLED_CODES = ("51503",)
_INSUFFICIENT_FUNDS_CODES = ("51008", "51004", "Insufficient")

def _sanitize_cl_ord_id(cl_ord_id: Optional[str]) -> Optional[str]:
    """Normalize an OKX client order id while preventing truncation collisions."""
    if not cl_ord_id:
        return None

    original = str(cl_ord_id)
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", original)
    if not cleaned:
        return None

    # Preserve already-valid short IDs exactly. For transformed or oversized
    # IDs, reserve eight characters for a deterministic digest of the source.
    if cleaned == original and len(cleaned) <= 32:
        return cleaned

    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:23]}{digest}"

def _is_entry_intent(intent: Any) -> bool:
    side = intent.side.value.lower()
    position_side = intent.position_side.lower()
    if position_side == "long":
        return side == "buy"
    if position_side == "short":
        return side == "sell"
    if position_side in {"net", ""}:
        return not getattr(intent, "reduce_only", False) and side == "buy"
    return False

def _to_existing_order(order: dict[str, Any]) -> ExistingOrder:
    return ExistingOrder(
        ord_id=order["id"],
        price=Decimal(str(order["price"])),
        size=Decimal(str(order["amount"])),
        side=order["side"].lower(),
        pos_side=order.get("info", {}).get("posSide", "net").lower(),
        cl_ord_id=_sanitize_cl_ord_id(order.get("clientOrderId")),
    )

def _to_grid_spec(intent: Any) -> GridOrderSpec:
    return GridOrderSpec(
        price=Decimal(str(intent.price)),
        size=Decimal(str(intent.size)),
        side=intent.side.value.lower(),
        pos_side=intent.position_side.lower(),
        cl_ord_id=_sanitize_cl_ord_id(intent.client_order_id),
    )

def _contains_error_code(error: Exception, codes: tuple[str, ...]) -> bool:
    message = str(error)
    return any(code.lower() in message.lower() for code in codes)


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BatchExecutionResult:
    statuses: tuple[ExecutionStatus, ...]
    results: tuple[Any, ...]


def _classify_batch_result(result: Any) -> ExecutionStatus:
    if not isinstance(result, dict):
        return ExecutionStatus.UNKNOWN

    info = result.get("info") or {}
    code = str(info.get("sCode", result.get("sCode", "0")))
    if code not in {"", "0"}:
        return ExecutionStatus.REJECTED

    if result.get("status") == "simulated" or result.get("id"):
        return ExecutionStatus.SUCCESS

    return ExecutionStatus.UNKNOWN

class OrderSyncEngine:
    """Serialize reconciliation and apply its delta in safe batches."""
    def __init__(self, exchange_engine: Any):
        self.engine = exchange_engine
        self._sync_lock = asyncio.Lock()
        self.reconciler = OrderReconciler(
            price_tolerance=_PRICE_TOLERANCE,
            size_tolerance=_SIZE_TOLERANCE,
        )

    async def sync_orders(
        self,
        target_intents: Iterable[Any],
        *,
        authorization: ExecutionAuthorization,
        is_limit_breached: bool = False,
    ) -> None:
        """Reconcile only an exact batch authorized by PreFlight."""
        target_intents = tuple(target_intents)
        authorization.require_for(target_intents)
        async with self._sync_lock:
            await self._sync_orders_locked(
                target_intents,
                authorization=authorization,
                is_limit_breached=is_limit_breached,
            )

    async def _sync_orders_locked(
        self,
        target_intents: Iterable[Any],
        *,
        authorization: ExecutionAuthorization,
        is_limit_breached: bool = False,
    ) -> None:
        try:
            authorization.require_for(target_intents)
            raw_open_orders = await self.engine.fetch_open_orders(config.SYMBOL)
            open_orders = [_to_existing_order(order) for order in raw_open_orders]
            target_orders = self._build_target_orders(target_intents, is_limit_breached=is_limit_breached)
            if is_limit_breached:
                logger.warning("⚠️ Pozisyon Limiti Aktif! Giriş emirleri filtrelendi. Sadece %s adet Kar-Al (TP) hedefi işlenecek.", len(target_orders))
            plan = self.reconciler.reconcile(target_orders, open_orders)
            if not plan.has_changes:
                return
            if plan.to_cancel_ids:
                logger.info("🗑️ İptal edilecek emirler: %s adet", len(plan.to_cancel_ids))
                await self._cancel_orders_async(plan.to_cancel_ids)
            if plan.to_amend_orders:
                logger.info("♻️ Güncellenecek (Amend) emirler: %s adet", len(plan.to_amend_orders))
                await self._amend_orders_async(plan.to_amend_orders)
            if plan.to_place_orders:
                logger.info("🆕 Yeni açılacak emirler: %s adet", len(plan.to_place_orders))
                await self._place_orders_async(plan.to_place_orders)
        except Exception as exc:
            logger.error("🚨 Emir senkronizasyonu sırasında hata: %s", exc)
            raise

    @staticmethod
    def _build_target_orders(target_intents: Iterable[Any], *, is_limit_breached: bool) -> list[GridOrderSpec]:
        return [
            _to_grid_spec(intent)
            for intent in target_intents
            if not (is_limit_breached and _is_entry_intent(intent))
        ]

    async def _cancel_orders_async(self, order_ids: list[str]) -> None:
        try:
            await self.engine.cancel_orders(order_ids, config.SYMBOL)
        except Exception as exc:
            logger.error("Toplu iptal hatası: %s", exc)
            raise

    async def _amend_single_order(self, spec: Any) -> Any:
        try:
            return await self.engine.exchange.edit_order(
                id=spec.ord_id, symbol=config.SYMBOL, type="limit", side=None,
                amount=float(spec.new_size), price=float(spec.new_price),
                params=self._amend_params(spec),
            )
        except Exception as exc:
            if _contains_error_code(exc, _FILLED_OR_CANCELLED_CODES) or "already been filled or canceled" in str(exc).lower():
                logger.info("ℹ️ Emir [%s] borsa tarafında zaten gerçekleşti/iptal edildi; Amend atlandı.", spec.ord_id)
                return None
            if _contains_error_code(exc, _INSUFFICIENT_FUNDS_CODES):
                logger.warning("⚠️ Yetersiz Margin/Bakiye (Amend). Emir [%s] güncellenemedi!", spec.ord_id)
                return None
            logger.error("Amend işlemi başarısız (ID: %s): %s", spec.ord_id, exc)
            return None

    @staticmethod
    def _amend_params(spec: Any) -> dict[str, str]:
        sanitized_id = _sanitize_cl_ord_id(spec.new_cl_ord_id)
        return {"newClOrdId": sanitized_id} if sanitized_id else {}

    async def _amend_orders_async(self, amend_specs: list[Any]) -> None:
        await self._run_in_batches(amend_specs, self._amend_batch, batch_size=_BATCH_SIZE, delay_seconds=_BATCH_DELAY_SECONDS)

    async def _amend_batch(self, batch: list[Any]) -> None:
        await asyncio.gather(*(self._amend_single_order(spec) for spec in batch), return_exceptions=True)

    async def _place_single_order(self, spec: Any) -> Any:
        try:
            return await self.engine.exchange.create_order(
                symbol=config.SYMBOL, type="limit", side=spec.side,
                amount=float(spec.size), price=float(spec.price),
                params=self._order_params(spec),
            )
        except Exception as exc:
            if _contains_error_code(exc, _INSUFFICIENT_FUNDS_CODES):
                logger.warning("⚠️ Yetersiz Margin/Bakiye (Place). %s %s @ %s emri açılamadı.", spec.side.upper(), spec.size, spec.price)
                return None
            logger.error("Yeni emir iletimi başarısız: %s", exc)
            return None

    async def _place_orders_async(self, place_specs: list[Any]) -> None:
        await self._run_in_batches(place_specs, self._place_batch, batch_size=_BATCH_SIZE, delay_seconds=_BATCH_DELAY_SECONDS)

    async def _place_batch(self, batch: list[Any]) -> BatchExecutionResult:
        orders = [
            {
                "side": spec.side,
                "amount": spec.size,
                "price": spec.price,
                "params": self._order_params(spec),
            }
            for spec in batch
        ]
        try:
            raw_results = await self.engine.create_orders(config.SYMBOL, orders)
        except Exception as exc:
            logger.error("Batch order result UNKNOWN: %s", exc)
            raise

        if not isinstance(raw_results, list) or len(raw_results) != len(batch):
            raise RuntimeError(
                "Batch order result is UNKNOWN: response count does not match request count"
            )

        statuses = tuple(_classify_batch_result(result) for result in raw_results)
        report = BatchExecutionResult(tuple(statuses), tuple(raw_results))
        if ExecutionStatus.UNKNOWN in report.statuses:
            raise RuntimeError(
                "Batch order result is UNKNOWN: one or more exchange results were ambiguous"
            )

        rejected = sum(status is ExecutionStatus.REJECTED for status in report.statuses)
        if rejected:
            logger.warning(
                "Batch order completed with %s/%s explicit rejections.",
                rejected,
                len(report.statuses),
            )
        return report

    @staticmethod
    async def _run_in_batches(items: list[Any], handler: Any, *, batch_size: int, delay_seconds: float) -> None:
        for start in range(0, len(items), batch_size):
            await handler(items[start:start + batch_size])
            if start + batch_size < len(items):
                await asyncio.sleep(delay_seconds)

    @staticmethod
    def _order_params(spec: Any) -> dict[str, str]:
        params = {"posSide": spec.pos_side}
        sanitized_id = _sanitize_cl_ord_id(spec.cl_ord_id)
        if sanitized_id:
            params["clientOrderId"] = sanitized_id
        return params
