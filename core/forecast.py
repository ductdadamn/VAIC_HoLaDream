"""
core/forecast.py (Dev 1 sở hữu logic, Dev 3 tra data thô) — load_external +
forecast_demand: booking curve (days_before_departure) + seasonal/holiday,
fallback về forecast_fallback (Seasonal + Moving Average + Holiday flag, đúng
tinh thần "Không dùng LSTM/Transformer") khi model lỗi hoặc thiếu dữ liệu.
external là bonus: nếu external rỗng, forecast vẫn chạy dựa trên lịch sử +
day_of_week.

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

_HIST_COLUMNS = ["status", "date", "origin_station", "destination_station", "days_before_departure"]
_GENERIC_DRIVER = "nhu cầu nền theo mùa/ngày trong tuần (không có yếu tố bất thường)"


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


def _external_flag_driver(external: dict) -> str | None:
    """Cờ external nổi bật nhất theo thứ tự ưu tiên (Tết > lễ > sự kiện > vé bay
    cao > bão > học sinh nghỉ) -> None nếu không có cờ nào bật, để nhường chỗ
    cho driver theo booking pace (forecast_demand) hoặc câu chung chung
    (forecast_fallback, qua _top_driver)."""
    if not external:
        return None
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
    if external.get("school_in_session") is False:
        return "học sinh nghỉ (nhu cầu du lịch gia đình tăng)"
    return None


def _top_driver(external: dict) -> str:
    """Luôn trả về string hiển thị được — explain.py ghép thẳng vào câu "Why", None
    sẽ in ra "...— None." trên UI. Không có cờ đặc biệt -> nhu cầu nền theo mùa/tuần.
    Dùng cho forecast_fallback (driver đồng nhất cho cả bảng, như bản gốc)."""
    return _external_flag_driver(external) or _GENERIC_DRIVER


def _season_multiplier(external: dict) -> float:
    """Nhân tố mùa vụ/external — dùng chung cho forecast_demand (booking curve)
    và forecast_fallback (seasonal+MA), để 2 model không lệch cách đọc external."""
    mult = 1.0
    if external.get("is_tet"):
        mult = 1.85
    elif external.get("is_holiday"):
        mult = 1.5
    elif external.get("event_flag"):
        mult = 1.15
    if external.get("flight_price_index", 100) >= 120:
        mult *= 1.08
    if external.get("weather") == "bão":
        mult *= 0.85
    if external.get("school_in_session") is False:
        mult *= 1.08
    return mult


def forecast_fallback(hist_df: pd.DataFrame, depart_date, external: dict | None = None) -> pd.DataFrame:
    """→ [origin, destination, expected_pax, confidence, top_driver]
    Seasonal + Moving Average + Holiday flag — lưới an toàn cuối, KHÔNG BAO GIỜ
    raise. forecast_demand() rơi về đây khi booking-curve model lỗi hoặc thiếu
    dữ liệu, để hệ không bao giờ đứng hình giữa demo."""
    external = external or {}
    depart_date = to_date_str(depart_date)
    dow = pd.Timestamp(depart_date).dayofweek

    if hist_df is None or not len(hist_df):
        hist_df = pd.DataFrame(columns=_HIST_COLUMNS)

    booked = hist_df[hist_df["status"] == "booked"].copy() if len(hist_df) else hist_df
    same_dow = booked.iloc[0:0]
    if len(booked):
        booked["dow"] = pd.to_datetime(booked["date"]).dt.dayofweek
        same_dow = booked[booked["dow"] == dow]

    driver = _top_driver(external)
    season_mult = _season_multiplier(external)

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


def _od_dbd_series(source: pd.DataFrame) -> pd.Series:
    if "days_before_departure" not in source.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(source["days_before_departure"], errors="coerce").dropna()


def _forecast_booking_curve(booked: pd.DataFrame, same_dow: pd.DataFrame, external: dict) -> pd.DataFrame:
    """Booking curve: bên cạnh seasonal+MA (giống forecast_fallback), khai thác
    days_before_departure (tốc độ đặt vé, trước đó không dùng tới) để:
    (a) OD có booking pace càng đều (cv thấp) -> confidence càng cao;
    (b) khi KHÔNG có cờ external nổi bật, top_driver mô tả đúng hành vi đặt vé
    của từng OD (đặt sớm / đặt sát ngày) thay vì 1 câu chung chung cho cả bảng."""
    global_dbd = _od_dbd_series(booked)
    global_mean = float(global_dbd.mean()) if len(global_dbd) else 16.0
    global_std = float(global_dbd.std()) if len(global_dbd) > 1 else 12.0

    flag_driver = _external_flag_driver(external)
    season_mult = _season_multiplier(external)

    rows = []
    for origin, destination in _all_od_pairs():
        od_all = booked[(booked.origin_station == origin) & (booked.destination_station == destination)]
        n_dates_all = od_all["date"].nunique()
        od_dow = same_dow[(same_dow.origin_station == origin) & (same_dow.destination_station == destination)]
        n_dates_dow = od_dow["date"].nunique()

        if n_dates_dow >= 3:
            source = od_dow
            base_pax = source.groupby("date").size().mean()
            sample_n = n_dates_dow
            cv = source.groupby("date").size().std() / max(base_pax, 1e-6) if n_dates_dow > 1 else 0.5
        elif n_dates_all >= 1:
            source = od_all
            base_pax = source.groupby("date").size().mean()
            sample_n = n_dates_all
            cv = 0.6
        else:
            source = od_all.iloc[0:0]
            base_pax = 1.5
            sample_n = 0
            cv = 0.8

        od_dbd = _od_dbd_series(source)
        pace_bonus = 0.0
        pace_driver = None
        if len(od_dbd) >= 3:
            od_mean = float(od_dbd.mean())
            od_std = float(od_dbd.std())
            dbd_cv = od_std / max(od_mean, 1e-6)
            pace_bonus = 0.05 * (1 - min(dbd_cv, 1.0))
            if global_std > 0:
                z = (od_mean - global_mean) / global_std
                if z >= 0.5:
                    pace_driver = f"khách đặt vé sớm cho chặng này (trung bình trước {od_mean:.0f} ngày)"
                elif z <= -0.5:
                    pace_driver = f"khách đặt sát ngày khởi hành (trung bình trước {od_mean:.0f} ngày)"

        driver = flag_driver or pace_driver or _GENERIC_DRIVER

        expected_pax = float(base_pax * season_mult)
        confidence = float(np.clip(
            0.5 + 0.4 * min(sample_n, 20) / 20 - 0.15 * min(cv, 1.0) + pace_bonus,
            0.35, 0.95,
        ))

        rows.append({
            "origin": origin,
            "destination": destination,
            "expected_pax": round(expected_pax, 1),
            "confidence": round(confidence, 2),
            "top_driver": driver,
        })

    result = pd.DataFrame(rows)
    if result.empty or result["top_driver"].isna().any() or (result["top_driver"] == "").any():
        raise ValueError("booking-curve forecast sinh top_driver rỗng/None")
    return result


def forecast_demand(hist_df: pd.DataFrame, depart_date, external: dict | None = None) -> pd.DataFrame:
    """→ [origin, destination, expected_pax, confidence, top_driver]
    hist_df: tickets.csv lịch sử (mọi train/ngày, trạng thái booked) dùng để ước lượng nền.
    origin/destination là TÊN GA — khớp gap_from/gap_to của core.inventory.

    Booking curve (days_before_departure) + seasonal/holiday. Model lỗi hoặc
    thiếu dữ liệu (thiếu cột, hist_df rỗng...) -> forecast_fallback (seasonal+MA
    thuần), KHÔNG BAO GIỜ để hệ đứng hình giữa demo."""
    external = external or {}
    depart_date_str = to_date_str(depart_date)

    if hist_df is None or not len(hist_df) or "days_before_departure" not in hist_df.columns:
        return forecast_fallback(hist_df, depart_date_str, external)

    try:
        dow = pd.Timestamp(depart_date_str).dayofweek
        booked = hist_df[hist_df["status"] == "booked"].copy()
        booked["dow"] = pd.to_datetime(booked["date"]).dt.dayofweek
        same_dow = booked[booked["dow"] == dow]

        result = _forecast_booking_curve(booked, same_dow, external)
        expected_cols = ["origin", "destination", "expected_pax", "confidence", "top_driver"]
        if list(result.columns) != expected_cols or len(result) != len(_all_od_pairs()):
            raise ValueError("booking-curve forecast sai schema")
        return result
    except Exception:
        return forecast_fallback(hist_df, depart_date_str, external)
