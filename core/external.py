"""load_external — bảng tra tĩnh external_signals.csv theo ngày."""
from __future__ import annotations
import functools
import pandas as pd

from .utils import to_date_str

EXTERNAL_CSV = "data/external_signals.csv"


@functools.lru_cache(maxsize=1)
def _load_table() -> pd.DataFrame:
    df = pd.read_csv(EXTERNAL_CSV)
    df["date"] = df["date"].astype(str)
    return df.set_index("date")


def load_external(depart_date) -> dict:
    """→ {is_holiday, is_tet, school_in_session, event_flag, weather, flight_price_index}
    Nếu ngày không có trong bảng (ngoài phạm vi dữ liệu) → giá trị mặc định trung tính."""
    key = to_date_str(depart_date)
    table = _load_table()
    if key not in table.index:
        return {
            "is_holiday": False, "is_tet": False, "school_in_session": True,
            "event_flag": False, "weather": "nắng", "flight_price_index": 100.0,
        }
    row = table.loc[key]
    return {
        "is_holiday": bool(row["is_holiday"]),
        "is_tet": bool(row["is_tet"]),
        "school_in_session": bool(row["school_in_session"]),
        "event_flag": bool(row["event_flag"]),
        "weather": str(row["weather"]),
        "flight_price_index": float(row["flight_price_index"]),
    }
