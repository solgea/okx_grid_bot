from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationResult:
    matched: bool
    code: str
    stopped: bool = False


class ShadowReconciler:
    """Phase-A reconciliation; mismatches stop, never auto-repair."""

    def reconcile(self, *, local_state: dict, exchange_state: dict | None = None) -> ReconciliationResult:
        if exchange_state is None:
            return ReconciliationResult(True, "SHADOW_REFERENCE_ONLY")
        if local_state != exchange_state:
            return ReconciliationResult(False, "E_RECONCILIATION", True)
        return ReconciliationResult(True, "MATCH")

    @staticmethod
    def is_bot_order(order: dict, prefix: str = "g") -> bool:
        cl_id = str(order.get("clientOrderId") or order.get("clOrdId") or "")
        return cl_id.startswith(prefix) and cl_id[1:].isalnum()

    def reconcile_orders(self, local_orders: list[dict], exchange_orders: list[dict]) -> ReconciliationResult:
        local = {o.get("id") for o in local_orders}
        managed = [o for o in exchange_orders if self.is_bot_order(o)]
        foreign = [o for o in exchange_orders if not self.is_bot_order(o)]
        if foreign:
            return ReconciliationResult(True, "UNMANAGED_ORDERS_IGNORED")
        if {o.get("id") for o in managed} != local:
            return ReconciliationResult(False, "E_RECONCILIATION", True)
        return ReconciliationResult(True, "MATCH")
