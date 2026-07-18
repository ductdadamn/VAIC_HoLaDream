"""
generate_policies — sinh 3 chính sách Thận trọng / Cân bằng / Quyết liệt.
Rule-based EMSR-inspired: giữ ghế ở chặng CÒN TRỐNG gần đầu tuyến để bảo vệ chỗ cho
khách đi DÀI chặng (giá trị cao hơn) sẽ xuất hiện sau, thay vì bán rẻ ngay cho khách
đi ngắn. Mức độ giữ (hold_ratio) + biên độ giá + ngưỡng chấp nhận gap tăng dần theo
khẩu vị rủi ro (Thận trọng < Cân bằng < Quyết liệt).
"""
from __future__ import annotations
import pandas as pd

from .contracts import Policy
from .reference_data import get_segments, STATION_ORDER, STATION_NAME
from .segments import find_gaps

_CONFIGS = [
    # name,          label_vi,     hold_ratio, price_mult, gap_conf_threshold, open_quota_at
    ("conservative", "Thận trọng", 0.05, 1.00, 0.75, "Mở bán ngay"),
    ("balanced",     "Cân bằng",   0.18, 1.05, 0.55, "Mở lại 48 giờ trước giờ khởi hành"),
    ("aggressive",   "Quyết liệt", 0.35, 1.12, 0.00, "Mở lại 24 giờ trước giờ khởi hành"),
]


def _pick_hold_segment(seat_matrix: pd.DataFrame, forecast_df: pd.DataFrame, segs: pd.DataFrame):
    occ = {seg["segment_id"]: (seat_matrix[seg["segment_id"]] == "SOLD").mean() for _, seg in segs.iterrows()}
    candidates = [seg for _, seg in segs.iterrows() if occ[seg["segment_id"]] < 0.75]
    if not candidates:
        candidates = [seg for _, seg in segs.iterrows()]

    best_seg, best_score, best_row = None, -1.0, None
    if forecast_df is not None and len(forecast_df):
        fc = forecast_df.copy()
        fc["dest_order"] = fc["destination"].map(STATION_ORDER)
        fc["orig_order"] = fc["origin"].map(STATION_ORDER)
        for seg in candidates:
            origin = seg["from_station"]
            sub = fc[(fc.origin == origin) & (fc.dest_order - fc.orig_order >= 3)]
            if sub.empty:
                continue
            sub = sub.assign(score=sub.expected_pax * sub.confidence)
            top = sub.sort_values("score", ascending=False).iloc[0]
            if top["score"] > best_score:
                best_score, best_seg, best_row = top["score"], seg, top

    if best_seg is None:
        best_seg = min(candidates, key=lambda s: occ[s["segment_id"]])

    return best_seg, occ[best_seg["segment_id"]], best_row


def generate_policies(forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame) -> list[Policy]:
    segs = get_segments()
    hold_seg, hold_occ, best_row = _pick_hold_segment(seat_matrix, forecast_df, segs)

    empty_in_seg = seat_matrix.loc[seat_matrix[hold_seg["segment_id"]] == "EMPTY", "seat_id"].tolist()

    if best_row is not None:
        hold_target = best_row["destination"]
        hold_confidence = float(best_row["confidence"])
    else:
        hold_target = STATION_ORDER and list(STATION_ORDER.keys())[-1]
        hold_confidence = 0.6

    all_gaps = find_gaps(seat_matrix)

    hold_label = f"{STATION_NAME[hold_seg['from_station']]}–{STATION_NAME[hold_seg['to_station']]}"

    policies = []
    for name, label, hold_ratio, price_mult, gap_thresh, quota in _CONFIGS:
        n_hold = 0
        if empty_in_seg:
            n_hold = max(1, round(hold_ratio * len(empty_in_seg))) if hold_ratio > 0 else 0
            n_hold = min(n_hold, len(empty_in_seg))
        hold_seats = empty_in_seg[:n_hold]

        if len(all_gaps):
            gaps = all_gaps[all_gaps["matched_demand"] >= gap_thresh]
        else:
            gaps = all_gaps
        gap_fills = gaps.to_dict("records")

        policies.append(Policy(
            name=name,
            label_vi=label,
            hold_seats=hold_seats,
            hold_segment_id=hold_seg["segment_id"],
            hold_segment_label=hold_label,
            hold_target_station=hold_target,
            hold_confidence=hold_confidence,
            price_multiplier=price_mult,
            open_quota_at=quota,
            gap_fills=gap_fills,
        ))
    return policies
