"""core/inventory.py — MỘT NGUỒN SỰ THẬT: mọi số liệu mức chặng derive từ tickets_df
qua aggregate_segments(). Không sinh/lưu bảng mức chặng riêng.
"""
import os

import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_STATIONS_CSV = os.path.join(_DATA_DIR, "stations.csv")

_FALLBACK_STATIONS = [
    ("Hà Nội", 0, 1),
    ("Thanh Hóa", 175, 2),
    ("Vinh", 319, 3),
    ("Đồng Hới", 522, 4),
    ("Huế", 688, 5),
    ("Đà Nẵng", 791, 6),
    ("Nha Trang", 1315, 7),
    ("Sài Gòn", 1726, 8),
]

_PRICE_PER_KM = 1500  # VND/km — ước lượng fare phẳng; find_gaps chỉ nhận seat_matrix
                      # theo contract nên không có giá vé thật để tra.
_SEG_SEP = " → "


def _load_stations() -> pd.DataFrame:
    """Đọc data/stations.csv (order tăng dần); fallback tuyến demo 8 ga nếu Dev 3 chưa sinh xong."""
    if os.path.exists(_STATIONS_CSV):
        stations = pd.read_csv(_STATIONS_CSV)
    else:
        stations = pd.DataFrame(_FALLBACK_STATIONS, columns=["name", "km_from_hanoi", "order"])
    return stations.sort_values("order").reset_index(drop=True)


def _segment_list(stations: pd.DataFrame) -> list:
    names = stations["name"].tolist()
    return list(zip(names[:-1], names[1:]))


def _order_map(stations: pd.DataFrame) -> dict:
    return dict(zip(stations["name"], stations["order"]))


def _filter_train_date(tickets_df: pd.DataFrame, train, date) -> pd.DataFrame:
    return tickets_df[(tickets_df["train_id"] == train) & (tickets_df["date"] == date)]


def aggregate_segments(tickets_df: pd.DataFrame, train, date) -> pd.DataFrame:
    """→ [segment_id, from_station, to_station, capacity, seats_sold, occupancy].
    Mỗi segment là 2 ga liền kề. seats_sold đếm ticket (status=booked) có
    [origin,destination] phủ qua đoạn đó. Đây là nguồn sự thật duy nhất cho mọi
    số liệu mức chặng — không hàm nào khác được tính occupancy riêng.
    """
    stations = _load_stations()
    segments = _segment_list(stations)
    order = _order_map(stations)

    trip = _filter_train_date(tickets_df, train, date)
    capacity = trip["seat_id"].nunique() or 1
    booked = trip[trip["status"] == "booked"]

    rows = []
    for i, (from_station, to_station) in enumerate(segments, start=1):
        lo, hi = order[from_station], order[to_station]
        covers = (booked["origin_station"].map(order) <= lo) & (booked["destination_station"].map(order) >= hi)
        seats_sold = booked.loc[covers, "seat_id"].nunique()
        rows.append({
            "segment_id": f"S{i}",
            "from_station": from_station,
            "to_station": to_station,
            "capacity": capacity,
            "seats_sold": seats_sold,
            "occupancy": round(seats_sold / capacity, 3),
        })
    return pd.DataFrame(rows)


def build_seat_matrix(tickets_df: pd.DataFrame, train, date) -> pd.DataFrame:
    """→ ma trận ghế × chặng (hàng=seat_id, cột=chặng), ô SOLD/EMPTY.
    HELD KHÔNG sinh ở đây: đó là quyết định của policy phủ lên ô EMPTY sau này,
    không phải trạng thái ghi trong tickets_df thô (giữ one-source-of-truth).
    """
    stations = _load_stations()
    segments = _segment_list(stations)
    order = _order_map(stations)

    trip = _filter_train_date(tickets_df, train, date)
    booked = trip[trip["status"] == "booked"]
    seat_ids = sorted(trip["seat_id"].unique())

    col_names = [f"{f}{_SEG_SEP}{t}" for f, t in segments]
    matrix = pd.DataFrame("EMPTY", index=seat_ids, columns=col_names)

    for _, row in booked.iterrows():
        lo, hi = order[row["origin_station"]], order[row["destination_station"]]
        for (from_station, to_station), col in zip(segments, col_names):
            seg_lo, seg_hi = order[from_station], order[to_station]
            if lo <= seg_lo and hi >= seg_hi:
                matrix.at[row["seat_id"], col] = "SOLD"

    matrix.index.name = "seat_id"
    return matrix


def find_gaps(seat_matrix: pd.DataFrame) -> pd.DataFrame:
    """→ [seat_id, gap_from, gap_to, matched_demand, extra_revenue].
    Quét từng hàng (ghế) tìm đoạn EMPTY liên tục kẹp giữa 2 đoạn SOLD.
    matched_demand = số ghế KHÁC đã bán trọn đúng đúng đoạn gap này — tín hiệu cầu
    quan sát trực tiếp từ ma trận (find_gaps chỉ nhận seat_matrix theo contract,
    không có forecast_df để join; generate_policies sẽ làm giàu thêm bằng forecast
    khi lắp gap_fills vào Policy).
    extra_revenue ước lượng bằng khoảng cách (km_from_hanoi) × giá/km cố định.
    """
    columns = list(seat_matrix.columns)
    segments = [tuple(col.split(_SEG_SEP)) for col in columns]
    stations = _load_stations()
    km = dict(zip(stations["name"], stations["km_from_hanoi"]))

    rows = []
    n = len(columns)
    for seat_id, values in zip(seat_matrix.index, seat_matrix.values):
        i = 0
        while i < n:
            if values[i] == "EMPTY":
                j = i
                while j < n and values[j] == "EMPTY":
                    j += 1
                if i > 0 and j < n and values[i - 1] == "SOLD" and values[j] == "SOLD":
                    gap_from = segments[i][0]
                    gap_to = segments[j - 1][1]
                    gap_cols = columns[i:j]
                    matched_demand = int((seat_matrix[gap_cols] == "SOLD").all(axis=1).sum())
                    extra_revenue = round(matched_demand * abs(km[gap_to] - km[gap_from]) * _PRICE_PER_KM, 0)
                    rows.append({
                        "seat_id": seat_id,
                        "gap_from": gap_from,
                        "gap_to": gap_to,
                        "matched_demand": matched_demand,
                        "extra_revenue": extra_revenue,
                    })
                i = j
            else:
                i += 1
    return pd.DataFrame(rows, columns=["seat_id", "gap_from", "gap_to", "matched_demand", "extra_revenue"])
