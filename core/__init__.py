"""Contract functions — app.py chỉ import và gọi các hàm dưới đây (không HTTP).

Sở hữu:
  core/inventory.py, core/policy.py, core/simulate.py, core/explain.py  — Dev 2 (thật)
  core/forecast.py (load_external + forecast_demand)                    — Dev 1/Dev 3
  core/overlay.py (apply_policy_overlay, chỉ dùng cho UI/heatmap)        — Dev 3
"""
from .inventory import (
    aggregate_segments, build_seat_matrix, find_gaps,
    segment_occupancy, segments_between, distance_km, route_fare, SEG_SEP,
)
from .policy import generate_policies, score_gaps
from .simulate import simulate, run_baseline, rank_policies
from .explain import explain
from .forecast import load_external, forecast_demand
from .overlay import apply_policy_overlay

__all__ = [
    "aggregate_segments", "build_seat_matrix", "find_gaps",
    "segment_occupancy", "segments_between", "distance_km", "route_fare", "SEG_SEP",
    "generate_policies", "score_gaps",
    "simulate", "run_baseline", "rank_policies",
    "explain",
    "load_external", "forecast_demand",
    "apply_policy_overlay",
]
