# Vietnam Railway United — Decision Copilot (VAIC 2026)

Decision Demo cho quản trị doanh thu đường sắt VN. Luồng: forecast cầu → sinh 3
policy giữ/bán ghế (Conservative/Balanced/Aggressive) → Gap Engine ghép chặng
trống → simulate (Monte Carlo) so với baseline → rank → explain → Manager
Approve/Override.

Không phải hệ thống thật — Streamlit monolith, các module gọi nhau bằng hàm
Python trực tiếp (không FastAPI/REST/login/React).

## Chạy thử

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python gen_data.py          # sinh data/tickets.csv, stations.csv, external_signals.csv
streamlit run app.py
```

## Cấu trúc

```
railmind/
  app.py            Streamlit dashboard (Dev 3)
  gen_data.py        sinh dữ liệu mẫu vào data/ (Dev 3)
  data/              tickets.csv, stations.csv, external_signals.csv
  core/
    forecast.py      forecast_demand, load_external (Dev 1)
    inventory.py     aggregate_segments, build_seat_matrix, find_gaps (Dev 2)
    policy.py        generate_policies (Dev 2)
    simulate.py       simulate, run_baseline, rank_policies (Dev 2)
    explain.py        explain (Dev 2)
    mocks.py         mock forecast cho walking skeleton (Dev 2)
  docs/screenshots/  ảnh chụp phiên AI collaboration
```

`tickets.csv` mức ghế là nguồn sự thật duy nhất — dữ liệu mức chặng luôn được
derive qua `aggregate_segments()`, không sinh riêng.
