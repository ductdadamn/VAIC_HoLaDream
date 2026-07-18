"""Chạy nhanh toàn bộ pipeline core trên ngày showcase để bắt lỗi trước khi build app.py."""
import pandas as pd
from core import (
    load_external, forecast_demand, aggregate_segments, build_seat_matrix,
    find_gaps, generate_policies, simulate, run_baseline, rank_policies, explain,
)

TRAIN = "SE3"
DATE = "2026-07-25"

tickets = pd.read_csv("data/tickets.csv")

ext = load_external(DATE)
print("external:", ext)

seg = aggregate_segments(tickets, TRAIN, DATE)
print("\naggregate_segments:")
print(seg)

matrix = build_seat_matrix(tickets, TRAIN, DATE)
print("\nseat_matrix shape:", matrix.shape)
print(matrix.head(3))

gaps = find_gaps(matrix)
print(f"\nfind_gaps: {len(gaps)} gaps found")
print(gaps.head(10))
assert "T3-15" in gaps["seat_id"].values, "T3-15 gap KHONG duoc tim thay!"
t15 = gaps[gaps.seat_id == "T3-15"].iloc[0]
assert t15.gap_from == "VIH" and t15.gap_to == "HUE", f"gap sai: {t15.gap_from}->{t15.gap_to}"
print("OK: T3-15 gap Vinh->Hue duoc tim thay dung.")

fc = forecast_demand(tickets, DATE, ext)
print("\nforecast_demand head:")
print(fc.sort_values("expected_pax", ascending=False).head(5))

policies = generate_policies(fc, matrix)
print(f"\n{len(policies)} policies sinh ra:")
for p in policies:
    print(f"  {p.name}: hold={len(p.hold_seats)} seats @ {p.hold_segment_label}, "
          f"target={p.hold_target_station}, conf={p.hold_confidence}, "
          f"price_mult={p.price_multiplier}, gaps_accepted={len(p.gap_fills)}")

baseline = run_baseline(fc, matrix)
print("\nbaseline:", baseline)

sim_results = {}
for p in policies:
    r = simulate(p, fc, matrix, n_runs=200)
    sim_results[p.name] = r
    print(f"\nsimulate({p.name}):", r)

ranking = rank_policies(sim_results)
print("\nranking:")
print(ranking)

print("\nexplain(balanced):")
bal_policy = [p for p in policies if p.name == "balanced"][0]
ex = explain(bal_policy, sim_results["balanced"], baseline, fc)
for k, v in ex.items():
    print(f"  {k}: {v}")

print("\n=== SMOKE TEST PASSED ===")
