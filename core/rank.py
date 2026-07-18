"""rank_policies — weighted score (không dùng Pareto/NSGA-II theo đúng plan)."""
from __future__ import annotations
import pandas as pd

W_REVENUE, W_OCC, W_PAXKM, W_RISK = 0.5, 0.2, 0.15, 0.15


def _norm(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi - lo < 1e-9:
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - lo) / (hi - lo)


def rank_policies(sim_results: dict[str, dict]) -> pd.DataFrame:
    """sim_results: {policy_name: SimResult dict} (3 policy, không gồm baseline).
    → DataFrame [policy, revenue, occupancy, pax_km, risk, confidence, score, rank]"""
    df = pd.DataFrame(list(sim_results.values()))

    score = (
        W_REVENUE * _norm(df["revenue"])
        + W_OCC * _norm(df["occupancy"])
        + W_PAXKM * _norm(df["pax_km"])
        - W_RISK * _norm(df["risk"])
    )
    df["score"] = score
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df[["policy", "revenue", "occupancy", "pax_km", "risk", "confidence", "score", "rank"]]
