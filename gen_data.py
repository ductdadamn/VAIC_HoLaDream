"""
Sinh dữ liệu demo mức GHẾ cho Vietnam Railway United (VAIC 2026).
Nguồn sự thật duy nhất = tickets.csv (mức ghế). Mọi số liệu chặng phải derive
qua core.inventory.aggregate_segments() — KHÔNG cấy sẵn số liệu chặng ở đây.

QUAN TRỌNG: core/inventory.py (Dev 2) nối chặng bằng TÊN GA (cột "name" của
stations.csv), không phải station_id — nên origin_station/destination_station
trong tickets.csv PHẢI là tên ga (vd "Hà Nội", "Vinh"), không phải mã ga
("HN", "VIH"). station_id chỉ dùng nội bộ ở gen_data.py này (tra cứu order/
khoảng cách/hạng giá) — không ghi ra tickets.csv.

Output: data/stations.csv, data/external_signals.csv, data/tickets.csv

Chạy: python gen_data.py
"""
from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd

from core.reference_data import (
    STATIONS_DF, TRAINS, HUB_WEIGHT, FARE_PER_KM, STATION_NAME,
    get_seat_catalog, get_segments, distance_km, n_segments,
    ORDERED_STATION_IDS,
)

SEED = 42
rng = np.random.default_rng(SEED)

TODAY = dt.date(2026, 7, 18)
HIST_START = TODAY - dt.timedelta(days=350)
FUTURE_END = TODAY + dt.timedelta(days=35)

SHOWCASE_TRAIN = "SE3"
SHOWCASE_DATE = TODAY + dt.timedelta(days=7)  # 2026-07-25 — "Ghế 15, toa 3, chặng Vinh–Huế"
GAP_SEAT_IDS = [
    "T3-15", "T3-22", "T5-8", "T5-19", "T6-3", "T6-27", "T2-11",
    "T9-14", "T9-30", "T4-5", "T7-17", "T1-9", "T8-21", "T10-6", "T2-25",
]

TRAIN_DEPART_TIME = {"SE1": "19:30", "SE3": "19:00"}

SEGMENTS = get_segments()  # 7 chặng liền kề, index 0..6
N_SEG = n_segments()

# ===================== LỊCH LỄ / MÙA VỤ (VN, 2025-07 .. 2026-08) =====================
HOLIDAY_RANGES = [
    ("2025-08-30", "2025-09-02", "Nghỉ lễ Quốc khánh 2/9"),
    ("2026-01-01", "2026-01-01", "Tết Dương lịch"),
    ("2026-02-14", "2026-02-22", "Tết Nguyên Đán Bính Ngọ"),
    ("2026-04-25", "2026-04-26", "Giỗ Tổ Hùng Vương"),
    ("2026-04-30", "2026-05-03", "Nghỉ lễ 30/4 - 1/5"),
]
TET_RANGE = ("2026-02-14", "2026-02-22")


def _in_range(d: dt.date, r) -> bool:
    a = dt.date.fromisoformat(r[0])
    b = dt.date.fromisoformat(r[1])
    return a <= d <= b


def holiday_info(d: dt.date):
    is_holiday = any(_in_range(d, r) for r in HOLIDAY_RANGES)
    is_tet = _in_range(d, TET_RANGE)
    return is_holiday, is_tet


def is_summer(d: dt.date) -> bool:
    return d.month in (6, 7, 8)


def season_multiplier(d: dt.date) -> float:
    is_holiday, is_tet = holiday_info(d)
    dow = d.weekday()  # 0=Mon .. 6=Sun
    is_weekend = dow in (4, 5, 6)  # thứ 6, 7, CN — cao điểm đi lại
    if is_tet:
        mult = 1.85
    elif is_holiday:
        mult = 1.5
    elif is_summer(d) and is_weekend:
        mult = 1.35
    elif is_summer(d):
        mult = 1.15
    elif is_weekend:
        mult = 1.15
    else:
        mult = 1.0
    noise = float(np.clip(rng.normal(1.0, 0.07), 0.8, 1.25))
    return mult * noise


def flight_price_index(d: dt.date) -> float:
    is_holiday, is_tet = holiday_info(d)
    base = 100.0
    if is_tet:
        base += 45
    elif is_holiday:
        base += 25
    elif is_summer(d) and d.weekday() in (4, 5, 6):
        base += 15
    base += rng.normal(0, 4)
    return round(float(base), 1)


def weather_for(d: dt.date) -> str:
    # mùa mưa bão miền Trung: tháng 9-11
    if d.month in (9, 10, 11):
        p = [0.45, 0.40, 0.15]  # nắng, mưa, bão
    elif d.month in (12, 1, 2):
        p = [0.55, 0.40, 0.05]
    else:
        p = [0.75, 0.23, 0.02]
    return rng.choice(["nắng", "mưa", "bão"], p=p)


def event_flag_for(d: dt.date, is_holiday: bool) -> bool:
    if is_holiday:
        return True
    return bool(rng.random() < 0.03)


def school_in_session(d: dt.date, is_tet: bool) -> bool:
    if is_summer(d) or is_tet:
        return False
    return True


# ===================== EXTERNAL SIGNALS =====================
def build_external_signals() -> pd.DataFrame:
    dates = pd.date_range(HIST_START, FUTURE_END, freq="D").date
    rows = []
    for d in dates:
        is_holiday, is_tet = holiday_info(d)
        rows.append({
            "date": d.isoformat(),
            "is_holiday": is_holiday,
            "is_tet": is_tet,
            "school_in_session": school_in_session(d, is_tet),
            "event_flag": event_flag_for(d, is_holiday),
            "weather": weather_for(d),
            "flight_price_index": flight_price_index(d),
        })
    return pd.DataFrame(rows)


# ===================== TRỌNG SỐ NHU CẦU THEO CHẶNG =====================
_seg_pop_raw = []
for _, seg in SEGMENTS.iterrows():
    a, b = seg["from_station"], seg["to_station"]
    _seg_pop_raw.append((HUB_WEIGHT[a] + HUB_WEIGHT[b]) / 2)
_pmin, _pmax = min(_seg_pop_raw), max(_seg_pop_raw)
SEG_BASE_OCC = [0.05 + 0.06 * (p - _pmin) / (_pmax - _pmin) for p in _seg_pop_raw]  # ~0.05-0.11


def segment_targets(season_mult: float) -> list[float]:
    out = []
    for base in SEG_BASE_OCC:
        noise = float(np.clip(rng.normal(1.0, 0.10), 0.7, 1.3))
        out.append(float(np.clip(base * season_mult * noise, 0.06, 0.97)))
    return out


# ===================== SINH VÉ CHO 1 (train, date) — QUY TRÌNH CHUNG =====================
def _make_ticket(counter, train, depart_date, seat_id, seat_class, origin, destination,
                  is_holiday, dow, min_days_before=0, max_days_before=120, status_bias=0.05):
    dist = distance_km(origin, destination)
    season = season_multiplier(depart_date)
    price_mult = 1 + (season - 1) * 0.6
    price = FARE_PER_KM[seat_class] * dist * price_mult * float(np.clip(rng.normal(1.0, 0.05), 0.85, 1.2))

    is_tet = holiday_info(depart_date)[1]
    scale = 28 if (is_tet or is_holiday) else 12
    dbd = int(np.clip(rng.exponential(scale), min_days_before, max_days_before))
    dbd = max(dbd, min_days_before)
    booking_date = depart_date - dt.timedelta(days=dbd)
    booking_time = dt.time(hour=int(rng.integers(6, 23)), minute=int(rng.integers(0, 60)))
    booking_ts = dt.datetime.combine(booking_date, booking_time)

    status = "available" if rng.random() < status_bias else "booked"

    counter[0] += 1
    return {
        "ticket_id": f"TK{counter[0]:07d}",
        "train_id": train,
        "date": depart_date.isoformat(),
        "departure_time": TRAIN_DEPART_TIME[train],
        "seat_id": seat_id,
        "seat_class": seat_class,
        "origin_station": STATION_NAME[origin],
        "destination_station": STATION_NAME[destination],
        "price": round(price, -2),  # làm tròn trăm đồng
        "status": status,
        "booking_timestamp": booking_ts.isoformat(sep=" "),
        "days_before_departure": dbd,
        "is_holiday": is_holiday,
        "day_of_week": dow,
    }


def _continue_prob(targets, seg_idx):
    if seg_idx >= len(targets):
        return 0.0
    return float(np.clip(0.55 + 0.4 * targets[seg_idx], 0.15, 0.9))


def generate_generic_day(counter, train, depart_date, seat_catalog, is_holiday):
    season = season_multiplier(depart_date)
    targets = segment_targets(season)
    dow = depart_date.weekday()
    rows = []
    for _, seat in seat_catalog.iterrows():
        seat_id, seat_class = seat["seat_id"], seat["seat_class"]
        i = 0
        while i < N_SEG:
            if rng.random() < targets[i]:
                start = i
                j = i
                while j + 1 < N_SEG and rng.random() < _continue_prob(targets, j + 1):
                    j += 1
                origin = ORDERED_STATION_IDS[start]
                destination = ORDERED_STATION_IDS[j + 1]
                rows.append(_make_ticket(counter, train, depart_date, seat_id, seat_class,
                                          origin, destination, is_holiday, dow))
                i = j + 1
            else:
                i += 1
    return rows


def generate_showcase_day(counter, train, depart_date, seat_catalog, is_holiday):
    """Cố tình tiêm điểm nghẽn: Vinh-Huế (SEG2 Vinh-DongHoi, SEG3 DongHoi-Hue) ~95%,
    và 15 ghế có 'gap kẹp giữa' (bán HN/Thanh Hóa->Vinh rồi Huế->xa hơn, trống Vinh-Huế)."""
    dow = depart_date.weekday()
    rows = []
    min_dbd = (depart_date - TODAY).days  # phải đặt trước hôm nay
    gap_set = set(GAP_SEAT_IDS)

    START_CHOICES_FULL = [0, 1, 2]
    START_W_FULL = [0.45, 0.30, 0.25]
    END_CHOICES_FULL = [3, 4, 5, 6]
    END_W_FULL = [0.15, 0.30, 0.25, 0.30]

    START_CHOICES_GAP1 = [0, 1]
    START_W_GAP1 = [0.55, 0.45]
    END_CHOICES_GAP2 = [4, 5, 6]
    END_W_GAP2 = [0.4, 0.3, 0.3]

    for _, seat in seat_catalog.iterrows():
        seat_id, seat_class = seat["seat_id"], seat["seat_class"]
        if seat_id in gap_set:
            start1 = rng.choice(START_CHOICES_GAP1, p=START_W_GAP1)
            origin1, dest1 = ORDERED_STATION_IDS[start1], ORDERED_STATION_IDS[2]  # ...-> Vinh
            rows.append(_make_ticket(counter, train, depart_date, seat_id, seat_class,
                                      origin1, dest1, is_holiday, dow,
                                      min_days_before=min_dbd, max_days_before=min_dbd + 40,
                                      status_bias=0.0))
            end2 = rng.choice(END_CHOICES_GAP2, p=END_W_GAP2)
            origin2, dest2 = ORDERED_STATION_IDS[4], ORDERED_STATION_IDS[end2 + 1]  # Huế -> ...
            rows.append(_make_ticket(counter, train, depart_date, seat_id, seat_class,
                                      origin2, dest2, is_holiday, dow,
                                      min_days_before=min_dbd, max_days_before=min_dbd + 40,
                                      status_bias=0.0))
        else:
            start = rng.choice(START_CHOICES_FULL, p=START_W_FULL)
            end = rng.choice(END_CHOICES_FULL, p=END_W_FULL)
            origin, destination = ORDERED_STATION_IDS[start], ORDERED_STATION_IDS[end + 1]
            rows.append(_make_ticket(counter, train, depart_date, seat_id, seat_class,
                                      origin, destination, is_holiday, dow,
                                      min_days_before=min_dbd, max_days_before=min_dbd + 40,
                                      status_bias=0.0))
    return rows


# ===================== CHỌN NGÀY KHỞI HÀNH ĐỂ SINH (đạt ~10k dòng, đủ mùa vụ) =====================
def pick_departure_dates():
    hist_dates = pd.date_range(HIST_START, TODAY - dt.timedelta(days=1), freq="16D").date.tolist()
    forced_holiday_dates = []
    for a, b, _ in HOLIDAY_RANGES:
        a_d, b_d = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        if b_d < TODAY:
            forced_holiday_dates.append(a_d + (b_d - a_d) // 2)
    hist_dates = sorted(set(hist_dates) | set(d for d in forced_holiday_dates if d >= HIST_START))

    future_daily = pd.date_range(TODAY, TODAY + dt.timedelta(days=14), freq="D").date.tolist()
    future_sparse = pd.date_range(TODAY + dt.timedelta(days=17), FUTURE_END, freq="4D").date.tolist()
    future_dates = sorted(set(future_daily) | set(future_sparse))

    return hist_dates, future_dates


def build_tickets() -> pd.DataFrame:
    counter = [0]
    hist_dates, future_dates = pick_departure_dates()
    all_rows = []
    catalogs = {t: get_seat_catalog(t) for t in TRAINS}

    for d in hist_dates:
        is_holiday = holiday_info(d)[0]
        for train in TRAINS:
            all_rows.extend(generate_generic_day(counter, train, d, catalogs[train], is_holiday))

    for d in future_dates:
        is_holiday = holiday_info(d)[0]
        for train in TRAINS:
            if train == SHOWCASE_TRAIN and d == SHOWCASE_DATE:
                all_rows.extend(generate_showcase_day(counter, train, d, catalogs[train], is_holiday))
            else:
                rows = generate_generic_day(counter, train, d, catalogs[train], is_holiday)
                min_dbd = (d - TODAY).days
                rows = [r for r in rows if r["days_before_departure"] >= min_dbd]
                all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    return df


# ===================== MAIN =====================
def main():
    import os
    os.makedirs("data", exist_ok=True)

    print("Sinh stations.csv ...")
    STATIONS_DF.to_csv("data/stations.csv", index=False, encoding="utf-8-sig")

    print("Sinh external_signals.csv ...")
    ext = build_external_signals()
    ext.to_csv("data/external_signals.csv", index=False, encoding="utf-8-sig")

    print("Sinh tickets.csv (mức ghế) ...")
    tickets = build_tickets()
    tickets.to_csv("data/tickets.csv", index=False, encoding="utf-8-sig")

    print(f"\n=== TỔNG QUAN ===")
    print(f"stations.csv: {len(STATIONS_DF)} ga")
    print(f"external_signals.csv: {len(ext)} ngày")
    print(f"tickets.csv: {len(tickets)} dòng, {tickets['seat_id'].nunique()} seat_id, "
          f"{tickets['date'].nunique()} ngày khởi hành, trains={sorted(tickets['train_id'].unique())}")

    print("\n--- head tickets.csv ---")
    print(tickets.head(8).to_string())

    print("\n--- kiểm tra showcase: SE3 ngày", SHOWCASE_DATE.isoformat(), "--- (dùng chính core.inventory thật)")
    from core.inventory import aggregate_segments, build_seat_matrix, find_gaps
    show = tickets[(tickets.train_id == SHOWCASE_TRAIN) & (tickets.date == SHOWCASE_DATE.isoformat())]
    print(f"số dòng vé: {len(show)}, số ghế có vé: {show['seat_id'].nunique()} / 300")

    seg = aggregate_segments(tickets, SHOWCASE_TRAIN, SHOWCASE_DATE.isoformat())
    print(seg.to_string(index=False))
    bottleneck = seg[seg.occupancy >= 0.9]
    assert len(bottleneck) >= 2, "BOTTLENECK KHONG XUAT HIEN qua core.inventory that!"
    print("OK: bottleneck >=90% xuat hien qua aggregate_segments() that cua Dev 2.")

    matrix = build_seat_matrix(tickets, SHOWCASE_TRAIN, SHOWCASE_DATE.isoformat())
    gaps = find_gaps(matrix)
    assert "T3-15" in gaps["seat_id"].values, "T3-15 KHONG duoc find_gaps() that tim thay!"
    t15 = gaps[gaps.seat_id == "T3-15"].iloc[0]
    print(f"OK: gap T3-15 tim thay qua find_gaps() that: {t15.gap_from} -> {t15.gap_to}, "
          f"+{t15.extra_revenue:,.0f}đ")

    print("\n--- ví dụ gap kẹp giữa: seat T3-15 ngày showcase ---")
    print(show[show.seat_id == "T3-15"][
        ["ticket_id", "seat_id", "origin_station", "destination_station", "status", "price"]
    ].to_string())

    print("\n--- external_signals mẫu (Tết) ---")
    print(ext[ext.is_tet].head(5).to_string())

    print("\nXong.")


if __name__ == "__main__":
    main()
