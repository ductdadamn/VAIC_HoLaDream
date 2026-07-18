# Bàn giao Forecast cho Dev 1 (~12h)

Skeleton đã đóng, cả hệ đang chạy trên **forecast tạm của Dev 3** (`core/forecast.py`).
Đọc file này 2 phút là vào việc, không cần dò lại code.

## 1. Hợp đồng hình dạng (QUAN TRỌNG NHẤT — không được lệch)

```python
load_external(depart_date) -> dict
forecast_demand(hist_df, depart_date, external) -> DataFrame
    # cột: [origin, destination, expected_pax, confidence, top_driver]
```

**Mẫu vàng** — output thật của bản tạm, chạy `python -c` trực tiếp trên data hiện tại
(dùng để đối chiếu: thay ruột xong, output phải cùng shape/kiểu dữ liệu như dưới):

```
load_external("2026-07-25")
-> {'is_holiday': False, 'is_tet': False, 'school_in_session': False,
    'event_flag': False, 'weather': 'mưa', 'flight_price_index': 106.3}

forecast_demand(tickets_df, "2026-07-25", ext).head(3):
origin destination  expected_pax  confidence                                                        top_driver
Hà Nội   Thanh Hóa          19.3        0.61 nhu cầu nền theo mùa/ngày trong tuần (không có yếu tố bất thường)
Hà Nội        Vinh          13.4        0.61 nhu cầu nền theo mùa/ngày trong tuần (không có yếu tố bất thường)
Hà Nội    Đồng Hới           7.9        0.62 nhu cầu nền theo mùa/ngày trong tuần (không có yếu tố bất thường)
```

`origin`/`destination` là **TÊN GA** (`"Hà Nội"`, `"Vinh"`...), khớp cột `name` của
`stations.csv` — không phải mã ga (`"HN"`, `"VIH"`). Lệch chỗ này thì gap-engine im
lặng về 0, không báo lỗi (đã có 1 bug thật kiểu này, xem `git log --oneline -- core/forecast.py`).

## 2. Bản tạm đang làm gì

Seasonal + moving average + holiday flag, đọc `data/external_signals.csv` thật
(không còn mock). Trong `core/forecast.py`:

- **Đã nối** vào `season_mult` ([forecast.py:95-105](../core/forecast.py#L95-L105)):
  `is_tet` (×1.85), `is_holiday` (×1.5), `event_flag` (×1.15), `flight_price_index≥120`
  (×1.08), `weather=="bão"` (×0.85).
- **Tra được nhưng CHƯA dùng làm driver**: `school_in_session` — `load_external()` trả
  đúng field này ([forecast.py:30-56](../core/forecast.py#L30-L56)) nhưng
  `forecast_demand()` không đọc tới. Việc để lại cho Dev 1 nếu thấy đáng làm.

## 3. top_driver — chỗ Dev 1 cần điền thêm

`_top_driver()` ([forecast.py:59-75](../core/forecast.py#L59-L75)) chọn theo thứ tự ưu
tiên cờ external (Tết > lễ > sự kiện > vé bay cao > bão), fallback về chuỗi mô tả
"nhu cầu nền theo mùa/ngày trong tuần" khi không có cờ nào — **KHÔNG BAO GIỜ trả
`None`** (từng có bug in ra "...— None." trên UI, đã fix, đừng lặp lại).

Đây là field mà `explain()` trích thẳng vào câu "Why" hiển thị cho Revenue Manager —
nếu Dev 1 nâng model (feature importance, SHAP...), `top_driver` phải luôn là 1
chuỗi tiếng Việt mô tả được, không phải tên feature kỹ thuật (`"flight_price_index"`)
hay `None`/`NaN`.

## 4. Chỗ KHÔNG được chạm

`forecast_demand`/`load_external` nằm sau contract — `core/policy.py` và `app.py` gọi
thẳng vào 2 hàm này. Dev 1 thay **ruột bên trong hàm**, giữ nguyên:
- Tên hàm, số lượng & thứ tự tham số.
- Tên cột output (`origin, destination, expected_pax, confidence, top_driver`).
- `origin`/`destination` là tên ga, không phải mã.

Đổi bất kỳ cái nào ở trên là vỡ `policy.py` (dùng `forecast_df["origin"]`,
`forecast_df["destination"]`, `forecast_df["confidence"]`) và `explain()` (dùng
`top_row['top_driver']`).

## 5. Ranh giới phạm vi (đây là phần của Dev 1, Technical Judge sẽ soi)

Được tự do nâng lên LightGBM / booking-curve / thêm feature — miễn là:
- Output vẫn đúng schema mục 1.
- Có **fallback** khi model/external lỗi hoặc thiếu data, để hệ không bao giờ đứng.
  Đặt tên `forecast_fallback` — **KHÔNG gọi là `"baseline"`**, chữ đó đã dành riêng cho
  `SELLNOW_BASELINE`/`run_baseline()` (baseline KPI so sánh policy, khác hẳn khái
  niệm này) — lẫn tên là lẫn nghĩa giữa 2 dev.

## 6. Verify sau khi thay ruột

```bash
python tests/smoke_test.py       # phải 6/6 PASS
python scripts/apptest_app.py    # phải 0 exception
```

6/6 pass + app không exception = forecast mới đã drop-in đúng, tín hiệu xanh để merge.
Không cần verify gì thêm ngoài 2 lệnh này.
