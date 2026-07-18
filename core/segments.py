"""
aggregate_segments / build_seat_matrix / find_gaps
Toàn bộ số liệu mức chặng được DERIVE từ tickets.csv mức ghế — không cấy sẵn.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .reference_data import get_segments, get_seat_catalog, STATION_ORDER, FARE_PER_KM, HUB_WEIGHT, distance_km
from .utils import to_date_str


def _filter_booked(tickets_df: pd.DataFrame, train: str, date) -> pd.DataFrame:
    d = to_date_str(date)
    df = tickets_df[
        (tickets_df["train_id"] == train)
        & (tickets_df["date"].astype(str).str[:10] == d)
        & (tickets_df["status"] == "booked")
    ]
    return df


def aggregate_segments(tickets_df: pd.DataFrame, train: str, date) -> pd.DataFrame:
    """→ [segment_id, from_station, to_station, capacity, seats_sold, occupancy]
    Với mỗi chặng liền kề, đếm số ghế (unique seat_id) có vé bao phủ trọn chặng đó."""
    segs = get_segments()
    capacity = len(get_seat_catalog(train))
    df = _filter_booked(tickets_df, train, date)

    rows = []
    if len(df):
        o = df["origin_station"].map(STATION_ORDER)
        dst = df["destination_station"].map(STATION_ORDER)
    for _, seg in segs.iterrows():
        if len(df):
            covers = df.loc[(o <= seg["order_from"]) & (dst >= seg["order_to"]), "seat_id"]
            seats_sold = int(covers.nunique())
        else:
            seats_sold = 0
        rows.append({
            "segment_id": seg["segment_id"],
            "from_station": seg["from_station"],
            "to_station": seg["to_station"],
            "capacity": capacity,
            "seats_sold": seats_sold,
            "occupancy": seats_sold / capacity if capacity else 0.0,
        })
    return pd.DataFrame(rows)


def build_seat_matrix(tickets_df: pd.DataFrame, train: str, date) -> pd.DataFrame:
    """→ [seat_id, coach, seat_class, SEG0..SEG6] — mỗi ô SOLD/EMPTY.
    (HELD là trạng thái do POLICY quyết định sau này — xem policy.apply_policy_overlay;
    ma trận gốc ở đây chỉ phản ánh dữ kiện đã bán, chưa áp chính sách giữ chỗ nào.)"""
    segs = get_segments()
    catalog = get_seat_catalog(train)
    df = _filter_booked(tickets_df, train, date)

    matrix = pd.DataFrame({"seat_id": catalog["seat_id"], "coach": catalog["coach"],
                            "seat_class": catalog["seat_class"]})
    for seg_id in segs["segment_id"]:
        matrix[seg_id] = "EMPTY"
    matrix = matrix.set_index("seat_id")

    if len(df):
        o = df["origin_station"].map(STATION_ORDER)
        dst = df["destination_station"].map(STATION_ORDER)
        for _, seg in segs.iterrows():
            mask = (o <= seg["order_from"]) & (dst >= seg["order_to"])
            sold_seats = df.loc[mask, "seat_id"].unique()
            sold_seats = matrix.index.intersection(sold_seats)
            matrix.loc[sold_seats, seg["segment_id"]] = "SOLD"

    return matrix.reset_index()


def _gap_value(seat_class: str, gap_from: str, gap_to: str) -> tuple[float, float]:
    """Ước lượng matched_demand (xác suất có khách khớp gap) + extra_revenue kỳ vọng."""
    pop = (HUB_WEIGHT[gap_from] + HUB_WEIGHT[gap_to]) / 2
    pop_min, pop_max = 0.95, 1.5
    ratio = float(np.clip((pop - pop_min) / (pop_max - pop_min), 0.0, 1.0))
    matched_demand = round(float(np.clip(0.55 + 0.35 * ratio, 0.5, 0.93)), 2)
    dist = distance_km(gap_from, gap_to)
    extra_revenue = round(FARE_PER_KM[seat_class] * dist * matched_demand, -3)
    return matched_demand, extra_revenue


def find_gaps(seat_matrix: pd.DataFrame) -> pd.DataFrame:
    """→ [seat_id, gap_from, gap_to, matched_demand, extra_revenue]
    Quét mỗi ghế theo thứ tự chặng, tìm các đoạn EMPTY bị KẸP GIỮA 2 đoạn SOLD
    (không tính đoạn trống ở đầu/cuối hành trình — đó không phải "gap ghép được")."""
    segs = get_segments()
    seg_ids = list(segs["segment_id"])
    seg_from = dict(zip(segs["segment_id"], segs["from_station"]))
    seg_to = dict(zip(segs["segment_id"], segs["to_station"]))
    n = len(seg_ids)

    rows = []
    for _, r in seat_matrix.iterrows():
        states = [r[sid] for sid in seg_ids]
        i = 0
        while i < n:
            if states[i] == "EMPTY":
                j = i
                while j + 1 < n and states[j + 1] == "EMPTY":
                    j += 1
                bounded_before = i > 0 and states[i - 1] == "SOLD"
                bounded_after = (j + 1 < n) and states[j + 1] == "SOLD"
                if bounded_before and bounded_after:
                    gap_from = seg_from[seg_ids[i]]
                    gap_to = seg_to[seg_ids[j]]
                    matched_demand, extra_revenue = _gap_value(r["seat_class"], gap_from, gap_to)
                    rows.append({
                        "seat_id": r["seat_id"],
                        "coach": r["coach"],
                        "gap_from": gap_from,
                        "gap_to": gap_to,
                        "matched_demand": matched_demand,
                        "extra_revenue": extra_revenue,
                    })
                i = j + 1
            else:
                i += 1
    cols = ["seat_id", "coach", "gap_from", "gap_to", "matched_demand", "extra_revenue"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).sort_values("extra_revenue", ascending=False).reset_index(drop=True)
