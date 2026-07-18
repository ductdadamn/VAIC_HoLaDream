"""tests/smoke_test.py — smoke test thuần Python (không cần pytest), chạy:
    python tests/smoke_test.py
Mục đích: bắt regression khi Dev 1 thay ruột forecast.py lúc 13h, hoặc khi Dev 3
nối tickets.csv thật vào — vẫn phải qua được các assert dưới đây. Test theo
SCHEMA/hành vi hợp đồng, không theo giá trị cụ thể của mock (để sống sót qua
lúc forecast_demand đổi ruột).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core.explain import explain
from core.forecast import forecast_demand, load_external
from core.inventory import aggregate_segments, build_seat_matrix, find_gaps
from core.mocks import mock_forecast
from core.policy import generate_policies
from core.simulate import rank_policies, run_baseline, simulate

TRAIN, DATE = "T1", "2026-09-02"


def _gap15_tickets() -> pd.DataFrame:
    """Ghế 15: SOLD Hà Nội->Vinh và Huế->Đà Nẵng, EMPTY ở giữa (Vinh-Huế) kẹp
    giữa 2 đoạn SOLD — ví dụ iconic của blueprint (mục 5.4/9)."""
    rows = [
        {"train_id": TRAIN, "date": DATE, "seat_id": 15, "origin_station": "Hà Nội", "destination_station": "Vinh", "status": "booked"},
        {"train_id": TRAIN, "date": DATE, "seat_id": 15, "origin_station": "Huế", "destination_station": "Đà Nẵng", "status": "booked"},
        {"train_id": TRAIN, "date": DATE, "seat_id": 20, "origin_station": "Vinh", "destination_station": "Huế", "status": "booked"},
        {"train_id": TRAIN, "date": DATE, "seat_id": 30, "origin_station": "Hà Nội", "destination_station": "Vinh", "status": "available"},
    ]
    return pd.DataFrame(rows)


def test_aggregate_segments():
    seg = aggregate_segments(_gap15_tickets(), TRAIN, DATE)
    assert list(seg.columns) == ["segment_id", "from_station", "to_station", "capacity", "seats_sold", "occupancy"]
    assert len(seg) == 7  # 8 ga demo -> 7 segment liền kề
    assert (seg["occupancy"] >= 0).all() and (seg["occupancy"] <= 1).all()
    print("OK  aggregate_segments: schema + occupancy trong [0,1]")


def test_seat_matrix_and_gaps():
    matrix = build_seat_matrix(_gap15_tickets(), TRAIN, DATE)
    assert set(matrix.values.flatten()) <= {"SOLD", "EMPTY"}
    assert matrix.loc[15, "Hà Nội → Thanh Hóa"] == "SOLD"
    assert matrix.loc[15, "Vinh → Đồng Hới"] == "EMPTY"

    gaps = find_gaps(matrix)
    assert list(gaps.columns) == ["seat_id", "gap_from", "gap_to", "matched_demand", "extra_revenue"]
    seat15_gap = gaps[gaps["seat_id"] == 15]
    assert len(seat15_gap) == 1
    row = seat15_gap.iloc[0]
    assert row["gap_from"] == "Vinh" and row["gap_to"] == "Huế"
    assert row["matched_demand"] == 1  # seat 20 đã bán trọn đúng Vinh-Huế
    assert row["extra_revenue"] == 369 * 1500  # route_fare(Vinh,Huế), KHÔNG nhân matched_demand
    print("OK  build_seat_matrix + find_gaps: ví dụ Ghế 15 Vinh–Huế đúng")


def test_forecast_stub_schema():
    external = load_external(DATE)
    assert isinstance(external, dict)
    forecast_df = forecast_demand(None, DATE, external)
    assert list(forecast_df.columns) == ["origin", "destination", "expected_pax", "confidence", "top_driver"]
    assert len(forecast_df) >= 5
    print("OK  forecast_demand/load_external: đúng schema (Dev 1 phải giữ khi thay ruột)")


def test_generate_policies_safety_margin_only():
    # Chỉ seat 15 có gap, KHÔNG seat nào khác chiếm đoạn Vinh-Huế -> bottleneck
    # occupancy = 0, cô lập đúng hiệu ứng của safety_margin (không bị cộng thêm
    # bottleneck_penalty như khi dùng _gap15_tickets() có seat 20).
    rows = [
        {"train_id": TRAIN, "date": DATE, "seat_id": 15, "origin_station": "Hà Nội", "destination_station": "Vinh", "status": "booked"},
        {"train_id": TRAIN, "date": DATE, "seat_id": 15, "origin_station": "Huế", "destination_station": "Đà Nẵng", "status": "booked"},
    ]
    matrix = build_seat_matrix(pd.DataFrame(rows), TRAIN, DATE)
    # p_long=0.65 border: Conservative (margin cao) phải BÁN, Aggressive (margin thấp) phải GIỮ
    forecast_df = pd.DataFrame([{"origin": "Vinh", "destination": "Huế", "expected_pax": 50, "confidence": 0.65, "top_driver": "test"}])
    policies = generate_policies(forecast_df, matrix)
    assert [p["name"] for p in policies] == ["Conservative", "Balanced", "Aggressive"]
    for p in policies:
        assert set(p.keys()) == {
            "name", "safety_margin", "hold_seats", "price_multiplier",
            "open_quota_at", "gap_fills", "last_call_hours", "fit_context",
        }
    by_name = {p["name"]: p for p in policies}
    assert 15 not in by_name["Conservative"]["hold_seats"]
    assert 15 in by_name["Aggressive"]["hold_seats"]
    print("OK  generate_policies: cùng 1 gap, chỉ đổi safety_margin -> quyết định khác nhau")


def test_simulate_and_rank():
    matrix = build_seat_matrix(_gap15_tickets(), TRAIN, DATE)
    forecast_df = mock_forecast(DATE)
    policies = generate_policies(forecast_df, matrix)
    baseline = run_baseline(forecast_df, matrix)
    assert set(baseline.keys()) == {"revenue", "occupancy", "pax_km", "risk", "confidence", "timeline"}
    assert baseline["confidence"] == 1.0  # sell-now không giữ gì -> không có bất định

    sim_results = [{"name": "Sell-now (baseline)", **baseline}]
    for p in policies:
        sim = simulate(p, forecast_df, matrix, n_runs=50)
        assert set(sim.keys()) == {"revenue", "occupancy", "pax_km", "risk", "confidence", "timeline"}
        assert 0.0 <= sim["confidence"] <= 1.0
        assert sim["revenue"] >= 0
        sim_results.append({"name": p["name"], **sim})

    ranked = rank_policies(sim_results)
    assert "score" in ranked.columns and "rank" in ranked.columns
    assert sorted(ranked["rank"].tolist()) == list(range(1, len(ranked) + 1))
    print("OK  simulate + run_baseline + rank_policies: schema + rank liên tục 1..N")


def test_explain_keys():
    matrix = build_seat_matrix(_gap15_tickets(), TRAIN, DATE)
    forecast_df = mock_forecast(DATE)
    policies = generate_policies(forecast_df, matrix)
    baseline = run_baseline(forecast_df, matrix)
    sim = simulate(policies[0], forecast_df, matrix, n_runs=50)
    result = explain(policies[0], sim, baseline, forecast_df)
    assert set(result.keys()) == {"what", "why", "benefit_vs_baseline", "risk", "confidence", "policy_fit"}
    assert all(isinstance(v, str) for v in result.values())
    print("OK  explain: đủ 6 field, đều là string hiển thị được")


def main():
    tests = [
        test_aggregate_segments,
        test_seat_matrix_and_gaps,
        test_forecast_stub_schema,
        test_generate_policies_safety_margin_only,
        test_simulate_and_rank,
        test_explain_keys,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} smoke test PASS")


if __name__ == "__main__":
    main()
