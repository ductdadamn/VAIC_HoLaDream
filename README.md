# Vietnam Railway United — Decision Copilot

Decision Demo (không phải hệ thống thật) cho bài toán quản lý doanh thu đường sắt VN.
Luồng: **Forecast → 3 policy giữ/bán ghế → Gap Engine ghép chặng → Simulate vs Baseline
→ Ranking → Explain (kèm rủi ro + độ tin cậy) → Manager Approve/Override**.

Stack: Python + Streamlit (monolith, không REST/login/React). Chạy trên
Streamlit Community Cloud.

## Chạy local

```bash
pip install -r requirements.txt
python gen_data.py          # sinh lại data/ nếu cần (đã commit sẵn, không bắt buộc)
streamlit run app.py
```

## Cấu trúc

```
gen_data.py        # sinh dataset mức ghế (nguồn sự thật duy nhất = data/tickets.csv)
data/               # tickets.csv, stations.csv, external_signals.csv
core/               # các hàm contract (forecast, aggregate, gap engine, policy, simulate, explain)
app.py              # Hero Screen dashboard (Streamlit)
scripts/            # smoke test / apptest headless cho core + app
```

## Contract (khoá schema + chữ ký hàm)

Nguồn sự thật duy nhất là `data/tickets.csv` ở **mức ghế**. Mọi số liệu mức chặng đều
`derive` qua `core.aggregate_segments()` — không có bảng mức chặng riêng.

```python
load_external(depart_date) -> dict
forecast_demand(hist_df, depart_date, external) -> DataFrame
aggregate_segments(tickets_df, train, date) -> DataFrame
build_seat_matrix(tickets_df, train, date) -> DataFrame       # SOLD / EMPTY
find_gaps(seat_matrix) -> DataFrame                             # gap ghép được (Gap Engine)
generate_policies(forecast_df, seat_matrix) -> list[Policy]     # Thận trọng/Cân bằng/Quyết liệt
simulate(policy, forecast_df, seat_matrix, n_runs=200) -> dict  # Monte Carlo
run_baseline(forecast_df, seat_matrix) -> dict                  # baseline Bán-ngay
rank_policies(sim_results) -> DataFrame
explain(policy, sim_result, baseline_result, forecast_df) -> dict
```

Xem `core/reference_data.py` cho định nghĩa ga/toa/ghế dùng chung.

## Kiểm thử nhanh (không cần trình duyệt)

```bash
python scripts/smoke_test_core.py     # kiểm tra pipeline core + gap Vinh-Huế 95%
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
