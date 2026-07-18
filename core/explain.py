"""
explain — sinh giải thích tiếng Việt What/Why/Benefit-vs-baseline/Risk/Confidence.
RỦI RO và ĐỘ TIN CẬY luôn có mặt trong dict trả về — không được ẩn (yêu cầu đề bài 6.6).
"""
from __future__ import annotations
import pandas as pd

from .contracts import Policy
from .reference_data import STATION_NAME
from .utils import fmt_vnd, fmt_pct

PRICE_CEILING_MULT = 1.20  # giá trần Nhà nước quy định: không vượt quá +20% giá vé cơ sở

POLICY_FIT_TEXT = {
    "conservative": "Hợp khi cần dòng tiền chắc chắn, ưu tiên an toàn (ngày thường, cầu thấp).",
    "balanced": "Hợp cho phần lớn các ngày vận hành thông thường — cân bằng doanh thu và rủi ro.",
    "aggressive": "Hợp cho cao điểm lễ/Tết khi cầu vượt cung rõ rệt, chấp nhận rủi ro để tối đa doanh thu.",
    "baseline": "Mốc đối chiếu — bán ngay toàn bộ, không giữ chỗ, không ghép gap.",
}


def _station(sid: str) -> str:
    return STATION_NAME.get(sid, sid)


def explain(policy: Policy, sim_result: dict, baseline_result: dict, forecast_df: pd.DataFrame) -> dict:
    """→ {what, why, benefit_vs_baseline, risk, confidence, policy_fit}"""

    # ---- WHAT ----
    what_parts = []
    if policy.hold_seats:
        what_parts.append(f"Giữ {len(policy.hold_seats)} ghế chặng {policy.hold_segment_label}")
    if policy.gap_fills:
        gap_rev = sum(g["extra_revenue"] for g in policy.gap_fills)
        what_parts.append(f"ghép {len(policy.gap_fills)} khoảng ghế trống (Gap Engine), thêm {fmt_vnd(gap_rev)}")
    if abs(policy.price_multiplier - 1.0) > 1e-6:
        what_parts.append(f"điều chỉnh giá x{policy.price_multiplier:.2f}, mở lại quota lúc: {policy.open_quota_at}")
    what = ". ".join(what_parts) + "." if what_parts else "Bán ngay toàn bộ ghế còn trống theo giá chuẩn."

    # ---- WHY ----
    top_driver = None
    if forecast_df is not None and len(forecast_df) and "top_driver" in forecast_df.columns:
        drivers = forecast_df["top_driver"].dropna()
        if len(drivers):
            top_driver = drivers.mode().iloc[0]
    target = _station(policy.hold_target_station) if policy.hold_target_station else ""
    why_bits = []
    if policy.hold_seats and target:
        why_bits.append(
            f"{fmt_pct(policy.hold_confidence, 0)} khả năng bán được vé đi {target} (giá trị cao hơn) "
            f"trong những ngày tới nếu giữ thay vì bán rẻ ngay bây giờ"
        )
    if top_driver:
        why_bits.append(f"nhu cầu đang tăng do {top_driver}")
    why = "; ".join(why_bits) + "." if why_bits else "Không có yếu tố bất thường — theo nhu cầu nền."

    # ---- BENEFIT VS BASELINE ----
    base_rev = baseline_result.get("revenue", 0) or 1
    delta_rev = sim_result["revenue"] - baseline_result.get("revenue", 0)
    delta_pct = delta_rev / base_rev if base_rev else 0.0
    benefit_vs_baseline = (
        f"Bán ngay (baseline): {fmt_vnd(baseline_result.get('revenue', 0))} (chắc chắn). "
        f"{policy.label_vi}: kỳ vọng {fmt_vnd(sim_result['revenue'])} "
        f"({'+' if delta_pct >= 0 else ''}{fmt_pct(delta_pct, 1)} so với baseline)."
    )

    # ---- RISK (bắt buộc hiển thị) ----
    if sim_result.get("risk", 0) > 0:
        risk = f"Nếu ghế giữ/gap không bán được: mất tối đa ~{fmt_vnd(sim_result['risk'])} doanh thu chắc chắn đã bỏ lỡ."
    else:
        risk = "Không giữ ghế nên không có rủi ro doanh thu bị mất — nhưng cũng không có phần thêm từ khách dài chặng."

    # ---- CONFIDENCE (bắt buộc hiển thị) ----
    confidence = {
        "value": sim_result.get("confidence", 0.0),
        "label": f"Độ tin cậy {fmt_pct(sim_result.get('confidence', 0.0), 0)}",
    }

    # ---- POLICY FIT + tuân thủ giá trần ----
    compliant = policy.price_multiplier <= PRICE_CEILING_MULT
    policy_fit = POLICY_FIT_TEXT.get(policy.name, "")
    compliance_note = (
        f"✓ Tuân thủ giá trần Nhà nước (≤ +{fmt_pct(PRICE_CEILING_MULT - 1, 0)})"
        if compliant else
        f"✗ VƯỢT giá trần Nhà nước (đang +{fmt_pct(policy.price_multiplier - 1, 0)}, trần +{fmt_pct(PRICE_CEILING_MULT - 1, 0)})"
    )

    return {
        "what": what,
        "why": why,
        "benefit_vs_baseline": benefit_vs_baseline,
        "risk": risk,
        "confidence": confidence,
        "policy_fit": policy_fit,
        "compliance": compliance_note,
        "compliant": compliant,
    }
