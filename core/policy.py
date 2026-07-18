"""core/policy.py — generate_policies: 3 policy sinh bằng ĐỔI safety_margin
(KHÔNG code 3 nhánh riêng). Hold vs Sell dùng bottleneck penalty (blueprint mục
11,12): GIỮ ghế nếu Hold_score > Sell_score × (1 + safety_margin).
"""
import pandas as pd

from core.inventory import find_gaps, route_fare, segment_occupancy, segments_between

_BOTTLENECK_WEIGHT = 0.5
_FALLBACK_CONFIDENCE = 0.3  # route không có trong forecast -> giả định cầu dài thấp
_GAP_FILL_COLUMNS = ["seat_id", "gap_from", "gap_to", "matched_demand", "extra_revenue"]

_POLICY_PRESETS = [
    {
        "name": "Conservative",
        "safety_margin": 0.35,
        "price_multiplier": 0.97,
        "open_quota_at": 48,
        "last_call_hours": 4,
        "fit_context": (
            "Hợp khi forecast độ tin cậy thấp, lịch sử biến động mạnh, thời tiết xấu, "
            "tỉ lệ hủy vé tăng — ưu tiên bán ngay lấy tiền mặt."
        ),
    },
    {
        "name": "Balanced",
        "safety_margin": 0.15,
        "price_multiplier": 1.0,
        "open_quota_at": 24,
        "last_call_hours": 3,
        "fit_context": (
            "Hợp khi cầu bình thường, tín hiệu lẫn lộn, độ tin cậy trung bình — "
            "điều chỉnh từ tốn theo booking pace."
        ),
    },
    {
        "name": "Aggressive",
        "safety_margin": 0.05,
        "price_multiplier": 1.08,
        "open_quota_at": 12,
        "last_call_hours": 2,
        "fit_context": (
            "Hợp khi cao điểm Tết/lễ/sự kiện, booking nhanh, độ tin cậy cao, ít áp lực "
            "đối thủ — ôm ghế đón khách chặng dài giá cao."
        ),
    },
]


def _p_long_haul(forecast_df: pd.DataFrame, origin: str, destination: str) -> float:
    match = forecast_df[(forecast_df["origin"] == origin) & (forecast_df["destination"] == destination)]
    if match.empty:
        return _FALLBACK_CONFIDENCE
    return float(match.iloc[0]["confidence"])


def _score_gap(gap_row, forecast_df: pd.DataFrame, occupancy: dict) -> pd.Series:
    """Sell_score = giá vé chặng ngắn (hop đầu của gap, chắc chắn thu được).
    Hold_score = P(khách dài, từ forecast) × giá vé chặng dài + bottleneck_penalty.
    bottleneck_penalty tỉ lệ occupancy của chặng nghẽn nhất mà gap này đi qua
    (occupancy càng cao, bán ngắn qua đó càng chặn mất vé dài giá cao).
    """
    gap_cols = segments_between(gap_row["gap_from"], gap_row["gap_to"])
    bottleneck_occupancy = max((occupancy.get(col, 0.0) for col in gap_cols), default=0.0)

    long_fare = route_fare(gap_row["gap_from"], gap_row["gap_to"])
    first_from, first_to = gap_cols[0].split(" → ") if gap_cols else (gap_row["gap_from"], gap_row["gap_to"])
    short_fare = route_fare(first_from, first_to)

    p_long = _p_long_haul(forecast_df, gap_row["gap_from"], gap_row["gap_to"])
    bottleneck_penalty = bottleneck_occupancy * long_fare * _BOTTLENECK_WEIGHT
    hold_score = p_long * long_fare + bottleneck_penalty
    return pd.Series({
        "sell_score": short_fare,
        "hold_score": hold_score,
        "bottleneck_penalty": bottleneck_penalty,
        "p_long": p_long,
        "long_fare": long_fare,
        "short_fare": short_fare,
        "short_to": first_to,
    })


def score_gaps(forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame) -> pd.DataFrame:
    """→ find_gaps() làm giàu thêm sell_score/hold_score/bottleneck_penalty/p_long/
    long_fare/short_fare/short_to. Public để simulate.py dùng lại CHÍNH cách tính
    này cho Monte Carlo (nhiễu p_long) thay vì tính lại từ đầu.
    """
    gaps = find_gaps(seat_matrix)
    extra_cols = ["sell_score", "hold_score", "bottleneck_penalty", "p_long", "long_fare", "short_fare", "short_to"]
    if gaps.empty:
        return gaps.reindex(columns=[*gaps.columns, *extra_cols])
    occupancy = segment_occupancy(seat_matrix)
    scores = gaps.apply(lambda row: _score_gap(row, forecast_df, occupancy), axis=1)
    return pd.concat([gaps, scores], axis=1)


def generate_policies(forecast_df: pd.DataFrame, seat_matrix: pd.DataFrame) -> list:
    """→ list[Policy]. Policy = {name, safety_margin, hold_seats, price_multiplier,
    open_quota_at, gap_fills, last_call_hours, fit_context}.
    """
    scored_gaps = score_gaps(forecast_df, seat_matrix)

    policies = []
    for preset in _POLICY_PRESETS:
        margin = preset["safety_margin"]
        if scored_gaps.empty:
            hold_seats, gap_fills = [], scored_gaps.reindex(columns=_GAP_FILL_COLUMNS)
        else:
            hold_mask = scored_gaps["hold_score"] > scored_gaps["sell_score"] * (1 + margin)
            hold_seats = scored_gaps.loc[hold_mask, "seat_id"].tolist()
            gap_fills = scored_gaps.loc[~hold_mask, _GAP_FILL_COLUMNS].reset_index(drop=True)

        policies.append({
            "name": preset["name"],
            "safety_margin": margin,
            "hold_seats": hold_seats,
            "price_multiplier": preset["price_multiplier"],
            "open_quota_at": preset["open_quota_at"],
            "gap_fills": gap_fills,
            "last_call_hours": preset["last_call_hours"],
            "fit_context": preset["fit_context"],
        })
    return policies
