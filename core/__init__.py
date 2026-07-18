"""Contract functions — app.py chỉ import và gọi các hàm dưới đây (không HTTP)."""
from .external import load_external
from .forecast import forecast_demand
from .segments import aggregate_segments, build_seat_matrix, find_gaps
from .policy import generate_policies, apply_policy_overlay
from .simulate import simulate, run_baseline
from .rank import rank_policies
from .explain import explain
from .contracts import Policy

__all__ = [
    "load_external", "forecast_demand", "aggregate_segments", "build_seat_matrix",
    "find_gaps", "generate_policies", "apply_policy_overlay", "simulate", "run_baseline",
    "rank_policies", "explain", "Policy",
]
