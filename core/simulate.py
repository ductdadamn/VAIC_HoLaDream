"""
simulate — Monte Carlo đơn giản (~200 lần) so sánh doanh thu chắc chắn (đã bán) với
phần doanh thu KHÔNG chắc chắn (ghế đang giữ + gap ghép được), mỗi phần được "tung
xu" theo xác suất (confidence / matched_demand) của nó ở mỗi lần chạy.

run_baseline = chính sách "Bán ngay" (không giữ ghế, không chủ động ghép gap) — dùng
làm mốc đối chiếu cho 3 policy.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .contracts import Policy
from .reference_data import FARE_PER_KM, get_segments, distance_km


def _matrix_revenue(seat_matrix: pd.DataFrame, price_multiplier: float = 1.0):
    segs = get_segments()
    revenue = 0.0
    pax_km = 0.0
    for _, seg in segs.iterrows():
        sold = seat_matrix[seat_matrix[seg["segment_id"]] == "SOLD"]
        if len(sold):
            fare_per_km = sold["seat_class"].map(FARE_PER_KM)
            revenue += float((fare_per_km * seg["distance_km"] * price_multiplier).sum())
            pax_km += len(sold) * seg["distance_km"]
    return revenue, pax_km


def simulate(policy: Policy, forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame, n_runs: int = 200) -> dict:
    """→ {revenue, occupancy, pax_km, risk, confidence, timeline}"""
    rng = np.random.default_rng(abs(hash(policy.name)) % (2**32 - 1))
    segs = get_segments()

    certain_revenue, certain_pax_km = _matrix_revenue(seat_matrix, policy.price_multiplier)
    total_cells = len(seat_matrix) * len(segs)
    n_sold_cells = int((seat_matrix[list(segs["segment_id"])] == "SOLD").to_numpy().sum())

    # --- ghế đang giữ: cược khách đi dài chặng (upside) so với bán ngay ở chặng giữ (downside) ---
    hold_seg_row = segs[segs["segment_id"] == policy.hold_segment_id]
    hold_seats_df = seat_matrix[seat_matrix["seat_id"].isin(policy.hold_seats)]
    n_hold = len(hold_seats_df)

    upside = np.zeros(n_hold)
    downside = np.zeros(n_hold)
    longhaul_dist = 0.0
    if n_hold and len(hold_seg_row):
        hold_seg = hold_seg_row.iloc[0]
        seg_dist = hold_seg["distance_km"]
        longhaul_dist = distance_km(hold_seg["from_station"], policy.hold_target_station) if policy.hold_target_station else seg_dist * 3
        longhaul_dist = max(longhaul_dist, seg_dist)
        for idx, (_, row) in enumerate(hold_seats_df.iterrows()):
            fare_km = FARE_PER_KM[row["seat_class"]]
            upside[idx] = fare_km * longhaul_dist * policy.price_multiplier
            downside[idx] = fare_km * seg_dist  # giá trị chắc chắn nếu bán ngay, không giữ

    hold_p = float(policy.hold_confidence) if n_hold else 0.0

    # --- gap ghép chặng ---
    gap_upside = np.array([g["extra_revenue"] for g in policy.gap_fills], dtype=float)
    gap_p = np.array([g["matched_demand"] for g in policy.gap_fills], dtype=float)
    n_gap = len(gap_upside)

    # --- Monte Carlo ---
    revenue_runs = np.full(n_runs, certain_revenue, dtype=float)
    filled_cells_runs = np.full(n_runs, n_sold_cells, dtype=float)

    if n_hold:
        hold_success = rng.random((n_runs, n_hold)) < hold_p
        revenue_runs += hold_success @ upside
        filled_cells_runs += hold_success.sum(axis=1)  # 1 chặng/ghế mỗi lần thành công

    if n_gap:
        gap_success = rng.random((n_runs, n_gap)) < gap_p[None, :]
        revenue_runs += gap_success @ gap_upside
        # mỗi gap có thể trải nhiều chặng liền kề — ước lượng 2 chặng/gap trung bình
        filled_cells_runs += gap_success.sum(axis=1) * 2

    mean_revenue = float(revenue_runs.mean())
    risk_amount = float(downside.sum())  # số tiền có thể mất nếu toàn bộ ghế giữ không bán được
    occupancy = float(np.clip(filled_cells_runs.mean() / total_cells, 0, 1)) if total_cells else 0.0

    # Độ tin cậy phản ánh PHẦN QUYẾT ĐỊNH (giữ ghế + gap) — phần đã bán chắc chắn
    # không cần "độ tin cậy" nên không hoà loãng vào đây.
    upside_total = float(upside.sum())
    gap_total = float(gap_upside.sum())
    speculative_total = upside_total + gap_total
    if speculative_total > 0:
        conf_num = upside_total * hold_p + float((gap_upside * gap_p).sum())
        confidence = float(np.clip(conf_num / speculative_total, 0.3, 0.95))
    else:
        confidence = 0.95  # không có phần đầu cơ nào (vd baseline) -> gần như chắc chắn

    avg_seg_dist = float(segs["distance_km"].mean())
    pax_km = certain_pax_km
    if n_hold:
        pax_km += hold_p * n_hold * longhaul_dist
    if n_gap:
        pax_km += float((gap_p * 2 * avg_seg_dist).sum())

    buckets = [14, 10, 7, 5, 3, 1, 0]
    timeline = [{
        "days_before_departure": b,
        "revenue": round(certain_revenue + (mean_revenue - certain_revenue) * (1 - b / 14), -3),
    } for b in buckets]

    return {
        "policy": policy.name,
        "revenue": round(mean_revenue, -3),
        "certain_revenue": round(certain_revenue, -3),
        "occupancy": round(occupancy, 4),
        "pax_km": round(pax_km, 1),
        "risk": round(risk_amount, -3),
        "confidence": round(confidence, 3),
        "timeline": timeline,
    }


def run_baseline(forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame) -> dict:
    """Baseline = Bán ngay: không giữ ghế, không chủ động ghép gap, giá chuẩn."""
    baseline_policy = Policy(
        name="baseline", label_vi="Bán ngay (Baseline)",
        hold_seats=[], hold_segment_id="", hold_segment_label="",
        hold_target_station="", hold_confidence=0.0,
        price_multiplier=1.0, open_quota_at="Bán ngay toàn bộ", gap_fills=[],
    )
    return simulate(baseline_policy, forecast_df, seat_matrix, n_runs=1)
