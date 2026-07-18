"""Kiểu dữ liệu dùng chung giữa các module core (đóng vai trò contract nội bộ)."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Policy:
    name: str                    # 'conservative' | 'balanced' | 'aggressive'
    label_vi: str                 # "Thận trọng" / "Cân bằng" / "Quyết liệt"
    hold_seats: list = field(default_factory=list)      # seat_id đang giữ lại chưa bán
    hold_segment_id: str = ""                            # SEGx đang giữ
    hold_segment_label: str = ""                          # "Hà Nội–Thanh Hóa"
    hold_target_station: str = ""                          # ga đích khách dài chặng dự kiến
    hold_confidence: float = 0.6                            # xác suất bán được khách dài chặng
    price_multiplier: float = 1.0
    open_quota_at: str = "Mở bán ngay"
    gap_fills: list = field(default_factory=list)   # list[dict]: seat_id, gap_from, gap_to, matched_demand, extra_revenue
