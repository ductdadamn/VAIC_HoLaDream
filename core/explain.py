"""core/explain.py — explain(): template + f-string tiếng Việt, KHÔNG để LLM ra
quyết định. Mọi con số lấy từ policy/sim_result/baseline_result thật, không bịa.
"""
import pandas as pd


def _pct_delta(current: float, base: float) -> float:
    if not base:
        return 0.0
    return (current - base) / base * 100


def explain(policy: dict, sim_result: dict, baseline_result: dict, forecast_df: pd.DataFrame) -> dict:
    """→ {what, why, benefit_vs_baseline, risk, confidence, policy_fit}."""
    n_hold = len(policy["hold_seats"])
    n_sell = len(policy["gap_fills"])

    what = (
        f"Chính sách {policy['name']}: giữ {n_hold} ghế cho khách chặng dài, "
        f"bán ngay {n_sell} khoảng trống ghép được, mở quota {policy['open_quota_at']}h "
        f"trước giờ chạy, last-call sau {policy['last_call_hours']}h nếu chưa khớp khách dài."
    )

    if not forecast_df.empty:
        top_row = forecast_df.loc[forecast_df["expected_pax"].idxmax()]
        why = (
            f"Cầu {top_row['origin']}–{top_row['destination']} dự báo cao nhất "
            f"({top_row['expected_pax']:.0f} khách, độ tin cậy {top_row['confidence']:.0%}) — "
            f"{top_row['top_driver']}."
        )
    else:
        why = "Không có dữ liệu forecast để xác định driver chính."

    revenue_delta = _pct_delta(sim_result["revenue"], baseline_result["revenue"])
    occupancy_delta = _pct_delta(sim_result["occupancy"], baseline_result["occupancy"])
    pax_km_delta = _pct_delta(sim_result["pax_km"], baseline_result["pax_km"])
    benefit_vs_baseline = (
        f"{revenue_delta:+.1f}% doanh thu, {occupancy_delta:+.1f}% lấp đầy, "
        f"{pax_km_delta:+.1f}% pax-km so với bán ngay (baseline)."
    )

    if n_hold:
        risk = (
            f"Đang giữ {n_hold} ghế cho khách chặng dài — nếu khách không xuất hiện trước "
            f"{policy['last_call_hours']}h trước giờ chạy, hệ thống tự chuyển các ghế này sang "
            f"bán chiết khấu last-call. Biến động doanh thu ước tính ±{sim_result['risk']:,.0f}đ "
            f"(độ lệch chuẩn qua mô phỏng Monte Carlo)."
        )
    else:
        risk = "Không giữ ghế nào — không có rủi ro last-call."

    return {
        "what": what,
        "why": why,
        "benefit_vs_baseline": benefit_vs_baseline,
        "risk": risk,
        "confidence": f"{sim_result['confidence']:.0%}",
        "policy_fit": policy["fit_context"],
    }
