"""
core/forecast.py (Dev 1 sở hữu logic, Dev 3 tra data thô) — load_external +
forecast_demand: fallback Seasonal + Moving Average + Holiday flag (đúng tinh thần
"Không dùng LSTM/Transformer"). external là bonus: nếu external rỗng, forecast vẫn
chạy dựa trên lịch sử + day_of_week.

origin/destination trả về là TÊN GA (khớp core/inventory.py: mọi nơi khác trong
core/ — gap_from/gap_to, seat_matrix columns — đều dùng tên ga, không phải mã ga).
"""
from __future__ import annotations
import functools
import itertools
import numpy as np
import pandas as pd

from .reference_data import ORDERED_STATION_IDS, STATION_NAME
from .utils import to_date_str

EXTERNAL_CSV = "data/external_signals.csv"
ORDERED_STATION_NAMES = [STATION_NAME[sid] for sid in ORDERED_STATION_IDS]


@functools.lru_cache(maxsize=1)
def _load_external_table() -> pd.DataFrame:
    df = pd.read_csv(EXTERNAL_CSV)
    df["date"] = df["date"].astype(str)
    return df.set_index("date")


def load_external(depart_date) -> dict:
    """→ {is_holiday, is_tet, school_in_session, event_flag, weather, flight_price_index}
    Tra data/external_signals.csv (bảng tĩnh, Dev 3 sinh). Ngày ngoài phạm vi dữ
    liệu -> giá trị mặc định trung tính (forecast vẫn chạy, không lỗi)."""
    key = to_date_str(depart_date)
    try:
        table = _load_external_table()
    except FileNotFoundError:
        table = pd.DataFrame()
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


def _all_od_pairs():
    return [(a, b) for a, b in itertools.combinations(ORDERED_STATION_NAMES, 2)]


def _top_driver(external: dict) -> str:
    """Luôn trả về string hiển thị được — explain.py ghép thẳng vào câu "Why", None
    sẽ in ra "...— None." trên UI. Không có cờ đặc biệt -> nhu cầu nền theo mùa/tuần."""
    if not external:
        return "nhu cầu nền theo lịch sử"
    if external.get("is_tet"):
        return "Tết Nguyên Đán"
    if external.get("is_holiday"):
        return "ngày nghỉ lễ"
    if external.get("event_flag"):
        return "sự kiện địa phương"
    if external.get("flight_price_index", 100) >= 120:
        return "giá vé máy bay tăng cao"
    if external.get("weather") == "bão":
        return "thời tiết xấu (giảm cầu)"
    return "nhu cầu nền theo mùa/ngày trong tuần (không có yếu tố bất thường)"


def forecast_demand(hist_df: pd.DataFrame, depart_date, external: dict | None = None) -> pd.DataFrame:
    """→ [origin, destination, expected_pax, confidence, top_driver]
    hist_df: tickets.csv lịch sử (mọi train/ngày, trạng thái booked) dùng để ước lượng nền.
    origin/destination là TÊN GA — khớp gap_from/gap_to của core.inventory."""
    external = external or {}
    depart_date = to_date_str(depart_date)
    dow = pd.Timestamp(depart_date).dayofweek

    if hist_df is None:
        hist_df = pd.DataFrame(columns=["status", "date", "origin_station", "destination_station"])

    booked = hist_df[hist_df["status"] == "booked"].copy() if len(hist_df) else hist_df
    same_dow = booked.iloc[0:0]
    if len(booked):
        booked["dow"] = pd.to_datetime(booked["date"]).dt.dayofweek
        same_dow = booked[booked["dow"] == dow]

    driver = _top_driver(external)
    season_mult = 1.0
    if external.get("is_tet"):
        season_mult = 1.85
    elif external.get("is_holiday"):
        season_mult = 1.5
    elif external.get("event_flag"):
        season_mult = 1.15
    if external.get("flight_price_index", 100) >= 120:
        season_mult *= 1.08
    if external.get("weather") == "bão":
        season_mult *= 0.85

    rows = []
    for origin, destination in _all_od_pairs():
        if len(booked):
            od_all = booked[(booked.origin_station == origin) & (booked.destination_station == destination)]
            n_dates_all = od_all["date"].nunique()
            od_dow = same_dow[(same_dow.origin_station == origin) & (same_dow.destination_station == destination)]
            n_dates_dow = od_dow["date"].nunique()
            if n_dates_dow >= 3:
                base_pax = od_dow.groupby("date").size().mean()
                sample_n = n_dates_dow
                cv = od_dow.groupby("date").size().std() / max(base_pax, 1e-6) if n_dates_dow > 1 else 0.5
            elif n_dates_all >= 1:
                base_pax = od_all.groupby("date").size().mean()
                sample_n = n_dates_all
                cv = 0.6
            else:
                base_pax = 1.5
                sample_n = 0
                cv = 0.8
        else:
            base_pax = 1.5
            sample_n = 0
            cv = 0.8

        expected_pax = float(base_pax * season_mult)
        confidence = float(np.clip(0.5 + 0.4 * min(sample_n, 20) / 20 - 0.15 * min(cv, 1.0), 0.35, 0.95))

        rows.append({
            "origin": origin,
            "destination": destination,
            "expected_pax": round(expected_pax, 1),
            "confidence": round(confidence, 2),
            "top_driver": driver,
        })

    return pd.DataFrame(rows)
