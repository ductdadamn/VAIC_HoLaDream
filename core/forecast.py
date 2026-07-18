"""core/forecast.py — stub cho walking skeleton (Dev 1 thay ruột buổi chiều, KHÔNG đổi chữ ký).
Chữ ký hàm đã khóa với PO — mọi module khác chỉ gọi forecast_demand/load_external qua đây.
"""
import pandas as pd

from core.mocks import mock_forecast

_DEFAULT_EXTERNAL = {
    "is_holiday": False,
    "is_tet": False,
    "event_flag": False,
    "weather": "nắng",
    "flight_price_index": 1.0,
}


def load_external(depart_date) -> dict:
    """→ {is_holiday, is_tet, event_flag, weather, flight_price_index}.
    STUB: trả giá trị mặc định cố định. Dev 1 thay bằng tra external_signals.csv.
    """
    return dict(_DEFAULT_EXTERNAL)


def forecast_demand(hist_df, depart_date, external) -> pd.DataFrame:
    """→ [origin, destination, expected_pax, confidence, top_driver].
    STUB: gọi mock_forecast để walking skeleton chạy. Dev 1 thay bằng model thật
    (LightGBM/XGBoost, fallback seasonal + MA), giữ nguyên schema trả về.
    """
    return mock_forecast(depart_date)
