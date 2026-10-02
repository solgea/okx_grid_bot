import pytest
from decimal import Decimal
from strategy.order_reconciler import OrderReconciler, GridOrderSpec, ExistingOrder, ReconciliationPlan

def test_no_open_orders():
    """Borsada açık emir yoksa, tüm hedeflerin yeni emir olarak işaretlenmesi gerekir."""
    reconciler = OrderReconciler()
    target_orders = [
        GridOrderSpec(price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long"),
        GridOrderSpec(price=Decimal("160.0"), size=Decimal("0.1"), side="sell", pos_side="short")
    ]
    open_orders = []

    plan = reconciler.reconcile(target_orders, open_orders)

    assert plan.has_changes is True
    assert len(plan.to_place_orders) == 2
    assert len(plan.to_cancel_ids) == 0
    assert len(plan.unmodified_orders) == 0

def test_perfect_match():
        """Borsadaki açık emirler ile hedefler birebir aynıysa, hiçbir aksiyon alınmamalıdır (rate-limit koruması)."""
        reconciler = OrderReconciler()
        target_orders = [
            GridOrderSpec(price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long")
        ]
        open_orders = [
            ExistingOrder(ord_id="ID1", price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long")
        ]
    
        plan = reconciler.reconcile(target_orders, open_orders)
    
        assert plan.has_changes is False
        assert len(plan.to_amend_orders) == 0  # <--- Hata buradaydı, 1 yazıyordu. 0 olmalı.
        assert len(plan.unmodified_orders) == 1 # Ekstra güvenlik testi
def test_size_mismatch_triggers_amend():
        """Fiyat doğru olsa bile emir büyüklüğü (size) değişmişse sistem emri Amend (düzenleme) işlemi ile güncellemelidir."""
        reconciler = OrderReconciler()
        target_orders = [
            GridOrderSpec(price=Decimal("150.0"), size=Decimal("0.2"), side="buy", pos_side="long") # Size 0.2 hedef
        ]
        open_orders = [
            ExistingOrder(ord_id="ID1", price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long") # Size 0.1 mevcut
        ]
    
        plan = reconciler.reconcile(target_orders, open_orders)
    
        assert plan.has_changes is True
        # to_place_orders yerine artık amend (düzenleme) bekliyoruz
        assert len(plan.to_amend_orders) == 1
        assert len(plan.to_place_orders) == 0
        assert plan.to_amend_orders[0].new_size == Decimal("0.2") # Doğru miktarın gönderildiğinden emin oluyoruz
def test_complete_mismatch():
    """Açık emirler tamamen yanlış seviyelerdeyse hepsi iptal edilip, yenileri girilmelidir."""
    reconciler = OrderReconciler()
    target_orders = [
        GridOrderSpec(price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long")
    ]
    open_orders = [
        ExistingOrder(ord_id="ID1", price=Decimal("999.0"), size=Decimal("0.1"), side="sell", pos_side="short")
    ]

    plan = reconciler.reconcile(target_orders, open_orders)

    assert plan.has_changes is True
    assert len(plan.to_place_orders) == 1
    assert plan.to_place_orders[0].price == Decimal("150.0")
    assert len(plan.to_cancel_ids) == 1
    assert plan.to_cancel_ids[0] == "ID1"
    assert len(plan.unmodified_orders) == 0

def test_partial_match():
    """Bazı emirler eşleşirken, bazılarının iptal edilip bazılarının yeni eklenmesi durumu."""
    reconciler = OrderReconciler()
    target_orders = [
        GridOrderSpec(price=Decimal("100.0"), size=Decimal("1.0"), side="buy", pos_side="long"), # Yeni eklenecek
        GridOrderSpec(price=Decimal("200.0"), size=Decimal("1.0"), side="sell", pos_side="long") # Mevcut
    ]
    open_orders = [
        ExistingOrder(ord_id="ID1", price=Decimal("200.0"), size=Decimal("1.0"), side="sell", pos_side="long"), # Kalacak
        ExistingOrder(ord_id="ID2", price=Decimal("300.0"), size=Decimal("1.0"), side="sell", pos_side="long")  # İptal edilecek
    ]

    plan = reconciler.reconcile(target_orders, open_orders)

    assert plan.has_changes is True
    assert len(plan.to_place_orders) == 1
    assert plan.to_place_orders[0].price == Decimal("100.0")
    
    assert len(plan.to_cancel_ids) == 1
    assert plan.to_cancel_ids[0] == "ID2"
    
    assert len(plan.unmodified_orders) == 1
    assert plan.unmodified_orders[0].ord_id == "ID1"

def test_size_mismatch_triggers_replacement():
        """Fiyat doğru olsa bile emir büyüklüğü (size) değişmişse sistem emri Amend (düzenleme) işlemi ile güncellemelidir."""
        reconciler = OrderReconciler()
        target_orders = [
            GridOrderSpec(price=Decimal("150.0"), size=Decimal("0.2"), side="buy", pos_side="long") # Size 0.2 hedef
        ]
        open_orders = [
            ExistingOrder(ord_id="ID1", price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long") # Size 0.1 mevcut
        ]
    
        plan = reconciler.reconcile(target_orders, open_orders)
    
        assert plan.has_changes is True
        
        # Eski beklentiyi siliyoruz: assert len(plan.to_place_orders) == 1
        # Yerine sisteminizin amend mantığını test ediyoruz:
        assert len(plan.to_amend_orders) == 1
        assert len(plan.to_place_orders) == 0
        assert len(plan.to_cancel_ids) == 0
        assert plan.to_amend_orders[0].new_size == Decimal("0.2") # Doğru miktarın gönderildiğinden emin oluyoruz

def test_price_tolerance_match():
    """Float bazlı mikroskobik fiyat kaymalarında tolerans sınırı içinde kalanlar eşleşmiş sayılmalıdır."""
    reconciler = OrderReconciler(price_tolerance=Decimal("0.0001"))
    
    # 150.0 ile 150.00005 tolerans dahilindedir, iptale gerek yok
    target_orders = [
        GridOrderSpec(price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long")
    ]
    open_orders = [
        ExistingOrder(ord_id="ID1", price=Decimal("150.00005"), size=Decimal("0.1"), side="buy", pos_side="long")
    ]

    plan = reconciler.reconcile(target_orders, open_orders)

    assert plan.has_changes is False
    assert len(plan.unmodified_orders) == 1

def test_client_order_id_priority():
    """Eğer cl_ord_id verildiyse, diğer parametrelere bakılmaksızın ilk olarak o ID üzerinden eşleşme yapılmalıdır."""
    reconciler = OrderReconciler()
    target_orders = [
        GridOrderSpec(price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long", cl_ord_id="MY_ORDER_1")
    ]
    open_orders = [
        ExistingOrder(ord_id="OKX_ID_1", price=Decimal("150.0"), size=Decimal("0.1"), side="buy", pos_side="long", cl_ord_id="MY_ORDER_1")
    ]

    plan = reconciler.reconcile(target_orders, open_orders)

    assert plan.has_changes is False
    assert len(plan.unmodified_orders) == 1
    assert plan.unmodified_orders[0].cl_ord_id == "MY_ORDER_1"