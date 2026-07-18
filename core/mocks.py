"""core/mocks.py — dữ liệu giả để walking skeleton chạy trước khi Dev 1 nối forecast thật.
Contract KHÔNG đổi: mock_forecast trả đúng schema của forecast_demand.
"""
import zlib

import numpy as np
import pandas as pd

_MOCK_ROUTES = [
    ("Hà Nội", "Vinh", 210, "school_in_session"),
    ("Hà Nội", "Đà Nẵng", 260, "is_holiday"),
    ("Vinh", "Huế", 90, "event_flag"),
    ("Huế", "Đà Nẵng", 140, "weather"),
    ("Đà Nẵng", "Nha Trang", 180, "flight_price_index"),
    ("Nha Trang", "Sài Gòn", 230, "is_tet"),
    ("Hà Nội", "Sài Gòn", 300, "is_holiday"),
]

_TOP_DRIVER_TEXT = {
    "school_in_session": "học sinh nghỉ hè, cầu tuyến ngắn tăng",
    "is_holiday": "trùng dịp lễ, cầu tuyến dài tăng mạnh",
    "event_flag": "có sự kiện địa phương dọc tuyến",
    "weather": "thời tiết xấu phía Bắc đẩy khách sang tuyến này",
    "flight_price_index": "giá vé máy bay cao, khách chuyển sang tàu",
    "is_tet": "cao điểm Tết, cầu tăng đột biến",
}


def stable_seed(*parts) -> int:
    """Hash ổn định qua các lần chạy process khác nhau (zlib.crc32 trên chuỗi
    UTF-8) — builtin hash() KHÔNG dùng được vì Python salt ngẫu nhiên hash(str)
    mỗi lần khởi động process, seed sẽ đổi dù cùng input."""
    data = "|".join(str(p) for p in parts).encode("utf-8")
    return zlib.crc32(data)


def mock_forecast(depart_date) -> pd.DataFrame:
    """→ DataFrame [origin, destination, expected_pax, confidence, top_driver].
    Seed theo depart_date để số liệu ổn định giữa các lần chạy demo cùng ngày.
    """
    seed = stable_seed(depart_date, "railmind-mock")
    rng = np.random.default_rng(seed)
    rows = []
    for origin, destination, base_pax, driver_key in _MOCK_ROUTES:
        rows.append({
            "origin": origin,
            "destination": destination,
            "expected_pax": round(float(base_pax * rng.uniform(0.85, 1.15)), 1),
            "confidence": round(float(rng.uniform(0.55, 0.9)), 2),
            "top_driver": _TOP_DRIVER_TEXT[driver_key],
        })
    return pd.DataFrame(rows)
