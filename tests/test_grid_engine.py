from decimal import Decimal
import pytest
import logging
# GridEngine'i projenizdeki dosyadan import ettiğinizi varsayıyoruz. 
# Örneğin grid_engine.py dosyasında ise:
from strategy.grid_engine import GridEngine, GridState

# Test loglarını gizlemek/görmek için opsiyonel ayar
logging.basicConfig(level=logging.WARNING)

# ==========================================
# 1. TEMEL YAPI VE HATA YÖNETİMİ TESTLERİ
# ==========================================

def test_valid_grid_creation():
    """1. Standart parametrelerle doğru grid üretimi."""
    engine = GridEngine(lower_price=100.0, upper_price=200.0, grid_count=5, contract_size=0.1, price_precision=2)
    assert engine.grid_step == 25.0
    assert engine.grid_levels == [100.0, 125.0, 150.0, 175.0, 200.0]
    assert engine.state == GridState.READY


def test_fsm_transitions_follow_position_context():
    engine = GridEngine(100, 200, 5, contract_size=0.1)

    assert engine.update_state(150, 0, 0) == GridState.READY
    assert engine.update_state(150, 0.1, 0) == GridState.ACCUMULATING
    assert engine.update_state(150, 0.1, 140) == GridState.DISTRIBUTING
    assert engine.previous_state == GridState.ACCUMULATING
    assert engine.state_reason == "Long pozisyon için kâr dağıtımı"


def test_fsm_pauses_on_invalid_market_or_grid():
    engine = GridEngine(100, 200, 5, contract_size=0.1)

    assert engine.update_state(0, 0, 0) == GridState.PAUSED
    assert engine.state_reason == "Geçersiz fiyat veya grid aralığı"

def test_invalid_grid_count():
    """2. grid_count 2'den küçükse otomatik 2'ye sabitlenmesi."""
    engine = GridEngine(lower_price=100.0, upper_price=200.0, grid_count=1, contract_size=0.1)
    assert engine.grid_count == 2
    assert engine.grid_step == 100.0
    assert engine.grid_levels == [100.0, 200.0]

def test_invalid_price_range():
    """3. Alt sınır, üst sınırdan büyük/eşitse çökme engellenmeli."""
    engine = GridEngine(lower_price=200.0, upper_price=100.0, grid_count=5, contract_size=0.1)
    assert engine.grid_step == 0.0
    # Tüm seviyeler eşit kalır, bot hatalı işlem açmaz
    assert engine.grid_levels == [200.0, 200.0, 200.0, 200.0, 200.0]

def test_duplicate_levels_due_to_low_precision():
    """4. Hassasiyet kaynaklı seviye çakışması tespiti."""
    # precision=2 olduğu için hepsi 0.0'a yuvarlanacak
    engine_low = GridEngine(0.0001, 0.0005, 5, 0.1, price_precision=2)
    assert engine_low.grid_levels == [0.0, 0.0, 0.0, 0.0, 0.0]
    
    # precision=4 ile sorunun çözüldüğünün doğrulanması
    engine_high = GridEngine(0.0001, 0.0005, 5, 0.1, price_precision=4)
    assert engine_high.grid_levels == [0.0001, 0.0002, 0.0003, 0.0004, 0.0005]

def test_very_wide_range():
    """19. Çok geniş fiyat aralıklarında stabilite."""
    engine = GridEngine(lower_price=1000.0, upper_price=100000.0, grid_count=5, contract_size=1.0)
    assert engine.grid_step == 24750.0
    assert engine.grid_levels == [1000.0, 25750.0, 50500.0, 75250.0, 100000.0]

# ==========================================
# 2. ATR (VOLATİLİTE) GÜNCELLEME TESTLERİ
# ==========================================

def test_atr_update_zero_atr():
    """5. ATR sıfır olduğunda sınırların korunması."""
    engine = GridEngine(100, 200, 5, 0.1)
    engine.update_dynamic_grid_with_atr(atr_value=0.0, multiplier=2.0, current_price=150.0)
    assert engine.lower_price == 100.0 # Değişmedi

def test_atr_update_negative_atr():
    """6. Negatif ATR durumunda işlemin reddedilmesi."""
    engine = GridEngine(100, 200, 5, 0.1)
    engine.update_dynamic_grid_with_atr(atr_value=-5.0, multiplier=2.0, current_price=150.0)
    assert engine.upper_price == 200.0 # Değişmedi

def test_atr_update_zero_multiplier():
    """7. Çarpan sıfır olduğunda sınırların korunması."""
    engine = GridEngine(100, 200, 5, 0.1)
    engine.update_dynamic_grid_with_atr(atr_value=10.0, multiplier=0.0, current_price=150.0)
    assert engine.lower_price == 100.0

def test_atr_update_negative_multiplier():
    """8. Negatif çarpan kullanımının reddedilmesi."""
    engine = GridEngine(100, 200, 5, 0.1)
    engine.update_dynamic_grid_with_atr(atr_value=10.0, multiplier=-1.5, current_price=150.0)
    assert engine.upper_price == 200.0

# ==========================================
# 3. SİPARİŞ OLUŞTURMA & POZİSYON TESTLERİ
# ==========================================

def test_get_orders_zero_position():
    """9. Pozisyon yokken standart nötr emirlerin dizilmesi."""
    engine = GridEngine(100, 200, 5, contract_size=0.1)
    orders = engine.get_target_orders(current_price=150.0, current_position_size=0.0, entry_price=0.0)
    
    # 150 seviyesi spread korumasından dolayı atlanır.
    # Enum yapınıza göre `.side.value` veya `.side` kısmını adapte edebilirsiniz
    assert getattr(orders[0].side, "value", str(orders[0].side)).lower() == "buy" 
    assert orders[0].price == Decimal("100.0")
    assert orders[0].size == Decimal("0.1")

def test_get_orders_positive_position_long():
    """10. Long pozisyondayken Kâr Al (TP) emirlerinin bölünmesi."""
    engine = GridEngine(100, 200, 5, contract_size=0.1)
    orders = engine.get_target_orders(current_price=150.0, current_position_size=0.15, entry_price=140.0)
    
    sell_orders = [o for o in orders if getattr(o.side, "value", str(o.side)).lower() == "sell"]
    
    # Sell 175 => 0.1 almalı, Sell 200 => kalan 0.05'i almalı
    assert sell_orders[0].price == Decimal("175.0")
    assert sell_orders[0].size == Decimal("0.1")
    assert sell_orders[1].price == Decimal("200.0")
    assert sell_orders[1].size == Decimal("0.05")

def test_get_orders_negative_position_short():
    """11. Short pozisyondayken Kâr Al (TP) emirlerinin bölünmesi."""
    engine = GridEngine(100, 200, 5, contract_size=0.1)
    orders = engine.get_target_orders(current_price=150.0, current_position_size=-0.15, entry_price=160.0)
    
    buy_orders = [o for o in orders if getattr(o.side, "value", str(o.side)).lower() == "buy"]
    
    # Seviyeler alttan (100) yukarı doğru okunduğu için önce 100, sonra 125 çalışır.
    assert buy_orders[0].price == Decimal("100.0")
    assert buy_orders[0].size == Decimal("0.1")
    assert buy_orders[1].price == Decimal("125.0")
    assert buy_orders[1].size == Decimal("0.05")

def test_get_orders_zero_entry_price():
    """12. Entry Price sıfırsa standart emirlerin dizilmesi (TP pasif)."""
    engine = GridEngine(100, 200, 5, contract_size=0.1)
    orders = engine.get_target_orders(current_price=150.0, current_position_size=0.5, entry_price=0.0)
    
    # Pozisyon olsa bile entry bilinmediğinden hepsi standart contract_size (0.1) olmalı
    for order in orders:
        assert order.size == Decimal("0.1")

# ==========================================
# 4. SMART MONEY CONCEPTS (SMC) TESTLERİ
# ==========================================

def test_smc_missing_data():
    """13. Eksik SMC verisi sistemin çökmesini engeller."""
    engine = GridEngine(100, 200, 5, 0.1)
    engine.update_grid_from_smc({}, current_price=150.0)
    engine.update_grid_from_smc(None, current_price=150.0)
    assert engine.lower_price == 100.0 # Sınırlar korunmalı

def test_smc_invalid_range():
    """14. VAL > VAH (Bozuk range) durumu yakalanmalı."""
    engine = GridEngine(100, 200, 5, 0.1)
    bad_smc = {'volume_profile': {'VAL': 200.0, 'VAH': 100.0}}
    engine.update_grid_from_smc(bad_smc, current_price=150.0)
    assert engine.lower_price == 100.0 # Güncellenmemeli

def test_smc_reversed_order_blocks():
    """15. Çelişkili Order Block verilerinde Volume Profile'a (Fallback) geçilmesi."""
    engine = GridEngine(50, 250, 5, 0.1)
    smc_data = {
        'order_blocks': {'bullish_ob': 180.0, 'bearish_ob': 120.0}, # Anormal: Bull > Bear
        'volume_profile': {'VAL': 100.0, 'VAH': 200.0}              # Normal
    }
    engine.update_grid_from_smc(smc_data, current_price=150.0)
    assert engine.lower_price == 100.0
    assert engine.upper_price == 200.0

def test_smc_out_of_bounds():
    """16. Fiyat tamamen aralık dışına çıktığında 'Avcı Modu'nun (OOB) devreye girmesi."""
    engine = GridEngine(50, 100, 5, 0.1, oob_min_width_pct=0.02, oob_buffer_pct=0.005)
    smc_data = {'volume_profile': {'VAL': 100.0, 'VAH': 110.0}}
    
    # Fiyat 150, alan 100-110. OOB Kalkanı devreye girmeli
    engine.update_grid_from_smc(smc_data, current_price=150.0)
    
    # Fiyatın (150) merkeze alınıp %2 adaptif genişlikle (3 birim = min 10 birim kullanılır) 145 - 155 çizilmeli
    assert engine.lower_price == 145.0
    assert engine.upper_price == 155.0

def test_smc_within_bounds_non_oob():
    """17. Fiyat güvenli alandayken SMC sınırlarının doğrudan uygulanması."""
    engine = GridEngine(0, 50, 5, 0.1)
    smc_data = {'volume_profile': {'VAL': 100.0, 'VAH': 200.0}}
    
    # Fiyat 150 (tam ortada)
    engine.update_grid_from_smc(smc_data, current_price=150.0)
    assert engine.lower_price == 100.0
    assert engine.upper_price == 200.0

def test_very_narrow_range():
    """18. Aşırı dar aralıklarda min_width_pct korumasının devreye girmesi."""
    engine = GridEngine(0, 50, 5, 0.1, oob_min_width_pct=0.02)
    smc_data = {'volume_profile': {'VAL': 100.0, 'VAH': 100.01}}
    
    # Genişlik sadece 0.01. Ancak 100.005 * %2 = ~2.0 birimlik minimum koruma kalkanı çalışmalı
    engine.update_grid_from_smc(smc_data, current_price=100.005)
    assert engine.lower_price == 100.0
    # Orijinal 100.01 yerine, kalkanın ürettiği +2 birimlik genleşme uygulanmalı
    assert round(engine.upper_price, 4) == 102.0001