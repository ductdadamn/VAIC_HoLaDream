"""core/simulate.py — simulate (bottleneck penalty + last-call, Monte Carlo
confidence) → run_baseline (gọi CHÍNH simulate() với policy Sell-now, KHÔNG viết
hàm mô phỏng thứ hai — so táo với táo) → rank_policies (weighted score).
"""
import numpy as np
import pandas as pd

from core.inventory import SEG_SEP, distance_km, route_fare, segments_between
from core.policy import score_gaps

_NOISE_PCT = 0.15  # Monte Carlo: nhiễu ±15% vào p_long mỗi run (blueprint mục 12)
_LAST_CALL_DISCOUNT = 0.7  # chiết khấu khi ép bán last-call (khách dài không tới)
_GAP_FILL_COLUMNS = ["seat_id", "gap_from", "gap_to", "matched_demand", "extra_revenue"]

_RANK_WEIGHTS = {"revenue": 0.5, "occupancy": 0.2, "confidence": 0.2, "risk": -0.1}


def _sold_runs(seat_matrix: pd.DataFrame) -> list:
    """Gộp các đoạn SOLD liên tục trên mỗi ghế thành 1 vé đã chốt (để tính doanh
    thu/pax-km đã thu thật, không đổi theo policy)."""
    columns = list(seat_matrix.columns)
    segments = [tuple(col.split(SEG_SEP)) for col in columns]
    n = len(columns)
    runs = []
    for seat_id, values in zip(seat_matrix.index, seat_matrix.values):
        i = 0
        while i < n:
            if values[i] == "SOLD":
                j = i
                while j < n and values[j] == "SOLD":
                    j += 1
                runs.append((segments[i][0], segments[j - 1][1]))
                i = j
            else:
                i += 1
    return runs


def _locked_in(seat_matrix: pd.DataFrame) -> tuple:
    """→ (revenue, pax_km) từ các vé đã bán thật trong seat_matrix — không phụ
    thuộc policy, giống nhau cho mọi policy và baseline."""
    revenue = pax_km = 0.0
    for frm, to in _sold_runs(seat_matrix):
        revenue += route_fare(frm, to)
        pax_km += distance_km(frm, to)
    return revenue, pax_km


def _sell_now_policy(forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame) -> dict:
    """Policy Sell-now: safety_margin +inf -> không bao giờ giữ, mọi gap bán ngay.
    Dùng để run_baseline() gọi CHÍNH simulate(), không viết mô phỏng thứ hai.
    """
    scored_gaps = score_gaps(forecast_df, seat_matrix)
    gap_fills = scored_gaps.reindex(columns=_GAP_FILL_COLUMNS) if scored_gaps.empty else scored_gaps[_GAP_FILL_COLUMNS]
    return {
        "name": "Sell-now (baseline)",
        "safety_margin": float("inf"),
        "hold_seats": [],
        "price_multiplier": 1.0,
        "open_quota_at": 0,
        "gap_fills": gap_fills,
        "last_call_hours": 0,
        "fit_context": "Baseline so sánh: bán ngay first-come-first-served, không giữ ghế nào.",
    }


def simulate(policy: dict, forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame, n_runs: int = 200) -> dict:
    """→ SimResult = {revenue, occupancy, pax_km, risk, confidence, timeline}.
    Monte Carlo n_runs lần, mỗi lần nhiễu ±15% vào p_long của các ghế đang GIỮ.
    confidence = tỉ lệ lần "giữ ghế" vẫn cho doanh thu kỳ vọng > "bán ngay" (mỗi
    ghế giữ, nếu khách dài không tới trước last_call_hours, tự động last-call
    bán chiết khấu — đúng luật last-call, không bịa số).
    """
    scored_gaps = score_gaps(forecast_df, seat_matrix)
    base_revenue, base_pax_km = _locked_in(seat_matrix)

    gap_fills = policy["gap_fills"]
    gap_fill_seats = set(gap_fills["seat_id"]) if not gap_fills.empty else set()
    sellnow_rows = scored_gaps[scored_gaps["seat_id"].isin(gap_fill_seats)] if not scored_gaps.empty else scored_gaps

    # Bán ngay = CHỈ chặng ngắn (hop đầu của gap, đúng định nghĩa Sell_score),
    # KHÔNG phải nguyên chiều dài gap — nếu bán được trọn gap ngay lập tức thì
    # không còn lý do gì để cân nhắc giữ ghế nữa.
    sellnow_fill_revenue = 0.0
    sellnow_fill_pax_km = 0.0
    for _, row in sellnow_rows.iterrows():
        sellnow_fill_revenue += row["short_fare"] * policy["price_multiplier"]
        sellnow_fill_pax_km += distance_km(row["gap_from"], row["short_to"])

    hold_set = set(policy["hold_seats"])
    held_gaps = scored_gaps[scored_gaps["seat_id"].isin(hold_set)] if not scored_gaps.empty else scored_gaps

    rng = np.random.default_rng()
    revenue_samples = []
    hold_wins = 0

    for _ in range(max(n_runs, 1)):
        run_revenue = base_revenue + sellnow_fill_revenue
        run_sellnow_counterfactual = base_revenue + sellnow_fill_revenue
        for _, row in held_gaps.iterrows():
            noise = rng.uniform(1 - _NOISE_PCT, 1 + _NOISE_PCT)
            p_long_noised = float(np.clip(row["p_long"] * noise, 0.0, 1.0))
            if rng.random() < p_long_noised:
                run_revenue += row["long_fare"] * policy["price_multiplier"]
            else:
                run_revenue += row["short_fare"] * _LAST_CALL_DISCOUNT  # last-call: khách dài không tới
            run_sellnow_counterfactual += row["short_fare"]

        revenue_samples.append(run_revenue)
        if run_revenue > run_sellnow_counterfactual:
            hold_wins += 1

    revenue = float(np.mean(revenue_samples))
    risk = float(np.std(revenue_samples))
    confidence = 1.0 if held_gaps.empty else hold_wins / len(revenue_samples)

    occupancy = _expected_occupancy(seat_matrix, sellnow_rows, held_gaps)
    pax_km = base_pax_km + sellnow_fill_pax_km + _expected_held_pax_km(held_gaps)

    timeline = [
        {"hours_before_departure": policy["open_quota_at"], "cumulative_revenue": round(base_revenue, 0)},
        {"hours_before_departure": policy["last_call_hours"], "cumulative_revenue": round(base_revenue + sellnow_fill_revenue, 0)},
        {"hours_before_departure": 0, "cumulative_revenue": round(revenue, 0)},
    ]

    return {
        "revenue": revenue,
        "occupancy": occupancy,
        "pax_km": pax_km,
        "risk": risk,
        "confidence": confidence,
        "timeline": timeline,
    }


def _expected_occupancy(seat_matrix: pd.DataFrame, sellnow_rows: pd.DataFrame, held_gaps: pd.DataFrame) -> float:
    """Occupancy trung bình theo chặng: nền hiện có + kỳ vọng đoạn được lấp thêm.
    Bán ngay chỉ lấp ĐÚNG 1 hop (chặng ngắn); held kỳ vọng theo p_long — cả gap
    nếu khách dài tới, chỉ 1 hop nếu last-call. Không lặp qua n_runs vì đây là kỳ
    vọng tuyến tính, không cần Monte Carlo như revenue/confidence.
    """
    n_segments = len(seat_matrix.columns) or 1
    capacity = len(seat_matrix) or 1
    base_occ_sum = (seat_matrix == "SOLD").sum().sum()

    filled_segment_units = float(len(sellnow_rows))  # mỗi hàng bán ngay lấp đúng 1 hop
    if not held_gaps.empty:
        for _, row in held_gaps.iterrows():
            long_span = len(segments_between(row["gap_from"], row["gap_to"]))
            filled_segment_units += row["p_long"] * long_span + (1 - row["p_long"]) * 1

    return min((base_occ_sum + filled_segment_units) / (n_segments * capacity), 1.0)


def _expected_held_pax_km(held_gaps: pd.DataFrame) -> float:
    if held_gaps.empty:
        return 0.0
    pax_km = 0.0
    for _, row in held_gaps.iterrows():
        long_km = distance_km(row["gap_from"], row["gap_to"])
        short_km = distance_km(row["gap_from"], row["short_to"])
        pax_km += row["p_long"] * long_km + (1 - row["p_long"]) * short_km
    return pax_km


def run_baseline(forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame) -> dict:
    """→ SimResult. BASELINE = policy Sell-now, BẮT BUỘC gọi CHÍNH simulate() ở
    trên — không viết hàm mô phỏng thứ hai, để so "táo với táo" (blueprint mục 6).
    """
    baseline_policy = _sell_now_policy(forecast_df, seat_matrix)
    return simulate(baseline_policy, forecast_df, seat_matrix)


def _normalize(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(1.0, index=series.index)
    return (series - lo) / (hi - lo)


def rank_policies(sim_results) -> pd.DataFrame:
    """→ DataFrame [..., score, rank]. sim_results: list[dict] mỗi dict = {"name",
    **SimResult}. Weighted score (revenue/occupancy/confidence dương, risk âm),
    KHÔNG Pareto/NSGA. rank=1 là tốt nhất.
    """
    df = pd.DataFrame(sim_results)
    score = pd.Series(0.0, index=df.index)
    for metric, weight in _RANK_WEIGHTS.items():
        score += weight * _normalize(df[metric])
    df["score"] = score
    df["rank"] = df["score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("rank").reset_index(drop=True)
