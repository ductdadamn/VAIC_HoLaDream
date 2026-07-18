"""
Dữ liệu tham chiếu dùng chung: ga, toa/ghế, chặng.
Đây là NGUỒN SỰ THẬT DUY NHẤT cho cấu trúc tuyến (8 ga, 2 mác tàu, ~300 ghế/tàu).
gen_data.py và core/*.py đều import từ đây để không bị lệch định nghĩa.
"""
from __future__ import annotations
import pandas as pd

# ===== Ga (tuyến trục Hà Nội - Sài Gòn, 8 ga) =====
STATIONS = [
    {"station_id": "HN", "name": "Hà Nội", "km_from_hanoi": 0, "order": 0},
    {"station_id": "THA", "name": "Thanh Hóa", "km_from_hanoi": 175, "order": 1},
    {"station_id": "VIH", "name": "Vinh", "km_from_hanoi": 319, "order": 2},
    {"station_id": "DHO", "name": "Đồng Hới", "km_from_hanoi": 522, "order": 3},
    {"station_id": "HUE", "name": "Huế", "km_from_hanoi": 688, "order": 4},
    {"station_id": "DNG", "name": "Đà Nẵng", "km_from_hanoi": 791, "order": 5},
    {"station_id": "NTR", "name": "Nha Trang", "km_from_hanoi": 1315, "order": 6},
    {"station_id": "SGN", "name": "Sài Gòn", "km_from_hanoi": 1726, "order": 7},
]

STATIONS_DF = pd.DataFrame(STATIONS)
STATION_ORDER = {s["station_id"]: s["order"] for s in STATIONS}
STATION_NAME = {s["station_id"]: s["name"] for s in STATIONS}
STATION_KM = {s["station_id"]: s["km_from_hanoi"] for s in STATIONS}
ORDERED_STATION_IDS = [s["station_id"] for s in sorted(STATIONS, key=lambda x: x["order"])]

# Ga "hub" hút khách (đầu tuyến + du lịch) dùng cho trọng số nhu cầu
HUB_WEIGHT = {
    "HN": 1.5, "SGN": 1.5,
    "HUE": 1.2, "DNG": 1.3, "NTR": 1.3,
    "THA": 1.0, "VIH": 1.05, "DHO": 0.95,
}

TRAINS = ["SE1", "SE3"]

# ===== Toa / ghế: 10 toa x 30 ghế = 300 ghế/tàu =====
COACH_LAYOUT = [
    # (coach_no_range, seat_class, seats_per_coach)
    (range(1, 4), "Ghế mềm điều hòa", 30),        # toa 1-3
    (range(4, 8), "Giường nằm khoang 6", 30),      # toa 4-7
    (range(8, 11), "Giường nằm khoang 4", 30),     # toa 8-10
]

# giá tham khảo VND / km theo hạng ghế
FARE_PER_KM = {
    "Ghế mềm điều hòa": 800,
    "Giường nằm khoang 6": 1000,
    "Giường nằm khoang 4": 1300,
}


def get_seat_catalog(train: str) -> pd.DataFrame:
    """→ [train_id, seat_id, coach, seat_no, seat_class] — danh mục ghế cố định của 1 mác tàu.
    seat_id dạng 'T{coach}-{seat_no}' vd 'T3-15' (Toa 3, Ghế 15)."""
    rows = []
    for coach_range, seat_class, n_seats in COACH_LAYOUT:
        for coach in coach_range:
            for seat_no in range(1, n_seats + 1):
                rows.append({
                    "train_id": train,
                    "seat_id": f"T{coach}-{seat_no}",
                    "coach": coach,
                    "seat_no": seat_no,
                    "seat_class": seat_class,
                })
    return pd.DataFrame(rows)


def get_segments() -> pd.DataFrame:
    """→ [segment_id, from_station, to_station, order_from, order_to, distance_km]
    7 chặng liền kề giữa 8 ga."""
    rows = []
    for i in range(len(ORDERED_STATION_IDS) - 1):
        a, b = ORDERED_STATION_IDS[i], ORDERED_STATION_IDS[i + 1]
        rows.append({
            "segment_id": f"SEG{i}",
            "from_station": a,
            "to_station": b,
            "order_from": i,
            "order_to": i + 1,
            "distance_km": STATION_KM[b] - STATION_KM[a],
        })
    return pd.DataFrame(rows)


def distance_km(origin: str, destination: str) -> int:
    return abs(STATION_KM[destination] - STATION_KM[origin])


def n_segments() -> int:
    return len(ORDERED_STATION_IDS) - 1
