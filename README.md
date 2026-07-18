# Vietnam Railway United — Decision Copilot

Decision Demo cho bài toán quản lý doanh thu đường sắt VN.
Luồng: **Forecast → 3 policy giữ/bán ghế → Gap Engine ghép chặng → Simulate vs Baseline
→ Ranking → Explain (kèm rủi ro + độ tin cậy) → Manager Approve/Override**.

Stack: Python + Streamlit (monolith architecture). Chạy trên Streamlit Community Cloud.

## Chạy local

```bash
pip install -r requirements.txt
python gen_data.py          # sinh data
streamlit run app.py
```

## Cấu trúc

```
gen_data.py          # sinh dataset mức ghế (nguồn sự thật duy nhất = data/tickets.csv)
data/                # tickets.csv, stations.csv, external_signals.csv
core/
  inventory.py       # (Dev 2) aggregate_segments, build_seat_matrix, find_gaps
  policy.py          # (Dev 2) generate_policies (safety_margin + bottleneck penalty)
  simulate.py        # (Dev 2) simulate, run_baseline, rank_policies (Monte Carlo)
  explain.py         # (Dev 2) explain — template tiếng Việt
  forecast.py        # (Dev 1/Dev 3) load_external + forecast_demand (seasonal + MA)
  overlay.py         # (Dev 3, UI-only) apply_policy_overlay — phủ HELD cho heatmap
  reference_data.py  # (Dev 3, nội bộ) ga/toa/ghế dùng để SINH data, không phải contract
app.py               # Hero Screen dashboard (Streamlit) — chỉ gọi core
tests/smoke_test.py  # smoke test chính thức của Dev 2 (schema/hành vi, không phụ thuộc mock)
scripts/             # apptest headless cho app.py (Dev 3)
```

## Contract (khoá schema + chữ ký hàm)

Nguồn sự thật duy nhất là `data/tickets.csv` ở **mức ghế**. Mọi số liệu mức chặng đều
`derive` qua `core.aggregate_segments()` — không có bảng mức chặng riêng.

**Quan trọng:** `origin_station`/`destination_station` trong tickets.csv, và mọi
`gap_from`/`gap_to`/`origin`/`destination` xuyên suốt `core/`, đều là **TÊN GA**
(khớp cột `name` của `stations.csv`, vd `"Hà Nội"`, `"Vinh"`) — **không phải**
`station_id` (`"HN"`, `"VIH"`). `core/inventory.py` nối chặng bằng tên ga; sai chỗ
này thì occupancy im lặng về 0 ở mọi chặng (không báo lỗi) — xem lịch sử fix trong
commit log nếu cần chi tiết.

```python
load_external(depart_date) -> dict
forecast_demand(hist_df, depart_date, external) -> DataFrame        # origin/destination = tên ga
aggregate_segments(tickets_df, train, date) -> DataFrame
build_seat_matrix(tickets_df, train, date) -> DataFrame             # index=seat_id, cột="A → B", SOLD/EMPTY
find_gaps(seat_matrix) -> DataFrame                                 # gap ghép được (Gap Engine)
generate_policies(forecast_df, seat_matrix) -> list[dict]           # Conservative/Balanced/Aggressive
simulate(policy, forecast_df, seat_matrix, n_runs=200) -> dict      # Monte Carlo
run_baseline(forecast_df, seat_matrix) -> dict                      # baseline Sell-now (gọi simulate())
rank_policies(sim_results: list[dict]) -> DataFrame
explain(policy, sim_result, baseline_result, forecast_df) -> dict   # 6 field, đều là string
apply_policy_overlay(seat_matrix, policy) -> DataFrame              # (Dev 3) phủ HELD cho UI
```

`policy["name"]` là `"Conservative"/"Balanced"/"Aggressive"` (tiếng Anh) — app.py tự
map sang nhãn tiếng Việt (`POLICY_LABEL_VI`) để hiển thị, không đổi ở core.

## Kiểm thử nhanh (không cần trình duyệt)

```bash
python tests/smoke_test.py            # smoke test chính thức của Dev 2: schema + hành vi core/
python scripts/apptest_app.py         # headless UI test: Approve / Override / chọn policy
```

## Demo flow (bất khả xâm phạm, ~3 click / 30-60s)

1. Click mác tàu nhấp nháy đỏ trong Exception Alert Feed (mặc định đã chọn sẵn ngày/tàu
   có sự cố quỹ ghế nặng nhất).
2. Xem heatmap tải theo chặng + 3 thẻ chính sách đối chiếu Baseline + Gap List.
3. Xem Explainability Panel (rủi ro + độ tin cậy luôn hiển thị) rồi bấm **APPROVE**
   hoặc **OVERRIDE** (chọn lý do bắt buộc) → ghi Audit Log.

## Deploy lên Streamlit Community Cloud

1. Push repo này lên GitHub (public).
2. Vào https://share.streamlit.io → New app → chọn repo, branch, file chính `app.py`.
3. Deploy — lấy Live URL, dùng URL đó để demo (không demo localhost).
