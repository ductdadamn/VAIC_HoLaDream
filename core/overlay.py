"""core/overlay.py (Dev 3) — apply_policy_overlay: phủ HELD lên seat_matrix cho
1 policy cụ thể, dùng để vẽ heatmap 3 màu SOLD/HELD/EMPTY.

core/inventory.build_seat_matrix() CHỦ ĐÍCH chỉ trả SOLD/EMPTY (one-source-of-
truth, không phụ thuộc policy nào — xem inventory.py:81-84). HELD là quyết định
của một policy cụ thể: trong core/policy.generate_policies(), 1 ghế được đưa vào
policy["hold_seats"] vì nó có 1 gap (từ find_gaps) mà hold_score > sell_score —
tức là HELD áp cho đúng những chặng nằm TRONG gap đó (gap_from..gap_to), không
phải toàn bộ hành trình của ghế. Hàm dưới đây không sửa core/inventory.py hay
core/policy.py — chỉ tiêu thụ output của find_gaps()/segments_between() để vẽ.
"""
from __future__ import annotations
import pandas as pd

from .inventory import find_gaps, segments_between


def apply_policy_overlay(seat_matrix: pd.DataFrame, policy: dict) -> pd.DataFrame:
    """→ bản copy của seat_matrix với các ô EMPTY thuộc gap đang GIỮ đổi thành HELD.
    Không đổi seat_matrix gốc — Gap Engine (find_gaps) vẫn luôn chạy trên EMPTY thật."""
    m = seat_matrix.copy()
    hold_set = set(policy.get("hold_seats", []))
    if not hold_set:
        return m

    gaps = find_gaps(seat_matrix)
    if gaps.empty:
        return m

    held = gaps[gaps["seat_id"].isin(hold_set)]
    for _, row in held.iterrows():
        for col in segments_between(row["gap_from"], row["gap_to"]):
            if col in m.columns and m.at[row["seat_id"], col] == "EMPTY":
                m.at[row["seat_id"], col] = "HELD"
    return m
