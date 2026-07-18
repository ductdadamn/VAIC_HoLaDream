"""
forecast_demand — fallback Seasonal + Moving Average + Holiday flag (đúng tinh thần
"Không dùng LSTM/Transformer"). external là bonus: nếu external rỗng, forecast vẫn
chạy dựa trên lịch sử + day_of_week.
"""
from __future__ import annotations
import itertools
import numpy as np
import pandas as pd

from .reference_data import ORDERED_STATION_IDS, STATION_ORDER
from .utils import to_date_str


def _all_od_pairs():
    ids = ORDERED_STATION_IDS
    return [(a, b) for a, b in itertools.combinations(ids, 2)]


def _top_driver(external: dict) -> str | None:
    if not external:
        return None
    if external.get("is_tet"):
        return "Tết Nguyên Đán"
    if external.get("is_holiday"):
        return "Ngày nghỉ lễ"
    if external.get("event_flag"):
        return "Sự kiện địa phương"
    if external.get("flight_price_index", 100) >= 120:
        return "Giá vé máy bay tăng cao"
    if external.get("weather") == "bão":
        return "Thời tiết xấu (giảm cầu)"
    return None


def forecast_demand(hist_df: pd.DataFrame, depart_date, external: dict | None = None) -> pd.DataFrame:
    """→ [origin, destination, expected_pax, confidence, top_driver]
    hist_df: tickets.csv lịch sử (mọi train/ngày, trạng thái booked) dùng để ước lượng nền.
    """
    external = external or {}
    depart_date = to_date_str(depart_date)
    dow = pd.Timestamp(depart_date).dayofweek

    booked = hist_df[hist_df["status"] == "booked"].copy() if len(hist_df) else hist_df
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
