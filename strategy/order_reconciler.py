from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Set, Dict
from collections import defaultdict


@dataclass(frozen=True)
class GridOrderSpec:
    """GridEngine tarafından üretilen hedef emir konfigürasyonu."""
    price: Decimal
    size: Decimal
    side: str        # "buy" | "sell"
    pos_side: str    # "long" | "short" | "net"
    cl_ord_id: Optional[str] = None


@dataclass(frozen=True)
class ExistingOrder:
    """Borsadaki (OKX) mevcut açık emrin durumu."""
    ord_id: str
    price: Decimal
    size: Decimal
    side: str
    pos_side: str
    cl_ord_id: Optional[str] = None


@dataclass(frozen=True)
class AmendOrderSpec:
    """Güncellenecek (amend) emrin taşıyacağı yeni parametreler."""
    ord_id: str
    new_price: Decimal
    new_size: Decimal
    new_cl_ord_id: Optional[str] = None


@dataclass
class ReconciliationPlan:
    """Borsaya iletilecek mutabakat planı (Delta)."""
    to_cancel_ids: List[str] = field(default_factory=list)
    to_place_orders: List[GridOrderSpec] = field(default_factory=list)
    to_amend_orders: List[AmendOrderSpec] = field(default_factory=list)
    unmodified_orders: List[ExistingOrder] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.to_cancel_ids or self.to_place_orders or self.to_amend_orders)


class OrderReconciler:
    """
    Hedef grid durumu ile borsadaki açık emirleri karşılaştırır.
    İptal/Yeni Emir (Cancel/Replace) sarmalını engellemek için Amend (Güncelleme)
    kullanır ve API limitlerini korur.
    """

    def __init__(self, price_tolerance: Decimal = Decimal("0.00000001"), size_tolerance: Decimal = Decimal("0.00000001")):
        self.price_tolerance = price_tolerance
        self.size_tolerance = size_tolerance

    def reconcile(
        self,
        target_orders: List[GridOrderSpec],
        open_orders: List[ExistingOrder]
    ) -> ReconciliationPlan:
        plan = ReconciliationPlan()
        
        # O(1) erişim için açık emirleri indeksle
        open_by_cl_ord_id: Dict[str, ExistingOrder] = {o.cl_ord_id: o for o in open_orders if o.cl_ord_id}
        
        matched_target_indices: Set[int] = set()
        matched_open_ids: Set[str] = set()

        # --- 1. FAZ: Client Order ID (cl_ord_id) Eşleştirmesi ---
        for t_idx, target in enumerate(target_orders):
            if target.cl_ord_id and target.cl_ord_id in open_by_cl_ord_id:
                open_ord = open_by_cl_ord_id[target.cl_ord_id]
                
                # Sadece yönler aynıysa amend edilebilir veya korunabilir
                if target.side.lower() == open_ord.side.lower() and target.pos_side.lower() == open_ord.pos_side.lower():
                    if self._is_exact_match(target, open_ord):
                        plan.unmodified_orders.append(open_ord)
                    else:
                        plan.to_amend_orders.append(AmendOrderSpec(
                            ord_id=open_ord.ord_id,
                            new_price=target.price,
                            new_size=target.size,
                            new_cl_ord_id=target.cl_ord_id
                        ))
                    
                    matched_target_indices.add(t_idx)
                    matched_open_ids.add(open_ord.ord_id)

        # --- 2. FAZ: Kalan Emirleri "Geri Dönüşüm" (Recycle) İçin Eşleştir ---
        remaining_targets = [t for i, t in enumerate(target_orders) if i not in matched_target_indices]
        remaining_opens = [o for o in open_orders if o.ord_id not in matched_open_ids]

        # Boştaki açık emirleri yönlerine (side, pos_side) göre grupla
        recyclable_opens = defaultdict(list)
        for o in remaining_opens:
            recyclable_opens[(o.side.lower(), o.pos_side.lower())].append(o)

        for target in remaining_targets:
            key = (target.side.lower(), target.pos_side.lower())
            
            # Eğer aynı yönde boştaki bir açık emir varsa, iptal etmek yerine onu hedefe taşı (Amend)
            if recyclable_opens[key]:
                open_ord = recyclable_opens[key].pop(0) 
                matched_open_ids.add(open_ord.ord_id)
                
                # Şans eseri (veya statik gridse) değerler tam uyuşuyorsa doğrudan koru
                if self._is_exact_match(target, open_ord) and target.cl_ord_id == open_ord.cl_ord_id:
                    plan.unmodified_orders.append(open_ord)
                else:
                    plan.to_amend_orders.append(AmendOrderSpec(
                        ord_id=open_ord.ord_id,
                        new_price=target.price,
                        new_size=target.size,
                        new_cl_ord_id=target.cl_ord_id
                    ))
            else:
                # Geri dönüştürülecek uygun emir kalmadıysa sıfırdan oluştur
                plan.to_place_orders.append(target)

        # --- 3. FAZ: Eşleşmeyen ve Dönüştürülemeyen Tüm Açık Emirleri İptal Et ---
        for open_ord in open_orders:
            if open_ord.ord_id not in matched_open_ids:
                plan.to_cancel_ids.append(open_ord.ord_id)

        return plan

    def _is_exact_match(self, target: GridOrderSpec, open_ord: ExistingOrder) -> bool:
        """Yön, fiyat ve lot miktarının toleranslar dahilinde eşleşip eşleşmediğini doğrular."""
        if target.side.lower() != open_ord.side.lower():
            return False
        if target.pos_side.lower() != open_ord.pos_side.lower():
            return False
        if abs(target.price - open_ord.price) > self.price_tolerance:
            return False
        if abs(target.size - open_ord.size) > self.size_tolerance:
            return False
        return True