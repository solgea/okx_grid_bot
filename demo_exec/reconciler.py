from dataclasses import dataclass

@dataclass(frozen=True)
class ReconciliationResult:
    matched: bool
    code: str

class ShadowReconciler:
    """Phase-A reconciliation is intentionally reference-only."""

    def reconcile(self, *, local_state: dict, exchange_state: dict | None = None) -> ReconciliationResult:
        if exchange_state is None:
            return ReconciliationResult(True, "SHADOW_REFERENCE_ONLY")
        if local_state != exchange_state:
            return ReconciliationResult(False, "E_RECONCILIATION")
        return ReconciliationResult(True, "MATCH")
