import pandas as pd

from strategy.grid_engine import GridEngine
from strategy.smc_engine import SMCVolumeEngine


def test_bullish_fvg_and_mss_are_detected():
    df = pd.DataFrame(
        {
            "open": [100, 101, 105, 106, 108],
            "high": [101, 102, 106, 109, 112],
            "low": [99, 100, 104, 105, 107],
            "close": [100, 101, 105, 108, 111],
        }
    )

    result = SMCVolumeEngine().analyze_structure(df)

    assert result["fvg"]["direction"] == "bullish"
    assert result["mss"] == "bullish"


def test_grid_bounds_include_bullish_fvg_and_mss_context():
    engine = GridEngine(100, 200, 5, 0.1)

    engine.update_grid_from_smc(
        {
            "volume_profile": {"VAL": 120, "VAH": 180},
            "order_blocks": {},
            "fvg": {"direction": "bullish", "lower": 110, "upper": 130},
            "mss": "bullish",
        },
        current_price=150,
    )

    assert engine.lower_price == 110
    assert engine.upper_price == 180
