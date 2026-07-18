"""
Vietnam Railway United — Decision Copilot
Hero Screen 1 màn hình. Streamlit monolith, gọi thẳng các hàm core/ (không REST/login).
Luồng demo: click SE3 đỏ -> xem heatmap + 3 policy vs baseline -> xem rủi ro + độ tin
cậy -> Approve/Override + audit log.
"""
from __future__ import annotations
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from core import (
    load_external, forecast_demand, aggregate_segments, build_seat_matrix,
    find_gaps, generate_policies, simulate, run_baseline, rank_policies, explain,
)
from core.reference_data import STATION_NAME, TRAINS, ORDERED_STATION_IDS
from core.utils import fmt_vnd, fmt_pct

OVERRIDE_REASONS = ["Thiên tai", "An sinh xã hội", "Lỗi hệ thống", "Nghi ngờ đầu cơ"]
POLICY_ORDER = ["conservative", "balanced", "aggressive"]
POLICY_COLOR = {"conservative": "#0284c7", "balanced": "#7c3aed", "aggressive": "#dc2626"}

st.set_page_config(
    page_title="VRU — Decision Copilot", page_icon="🚆", layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================ CSS ============================================================
st.markdown("""
<style>
@keyframes blinkred {
  0%, 100% { background-color:#fee2e2; box-shadow:0 0 0 0 rgba(220,38,38,.5); }
  50% { background-color:#fca5a5; box-shadow:0 0 0 6px rgba(220,38,38,0); }
}
.alert-row-blink button {
  animation: blinkred 1.1s infinite;
  border: 2px solid #dc2626 !important;
  color:#991b1b !important;
  font-weight:700 !important;
}
.alert-row-ok button {
  border: 1px solid #22c55e !important;
  color:#166534 !important;
}
div.st-key-approve_btn button {
  background-color:#16a34a !important; border-color:#16a34a !important; color:white !important;
  font-size:1.35rem !important; font-weight:800 !important; padding:0.9rem 0 !important;
}
div.st-key-approve_btn button:hover { background-color:#15803d !important; }
div.st-key-override_btn button {
  background-color:#dc2626 !important; border-color:#dc2626 !important; color:white !important;
  font-size:1.35rem !important; font-weight:800 !important; padding:0.9rem 0 !important;
}
div.st-key-override_btn button:hover { background-color:#b91c1c !important; }
.policy-card {
  border-radius:12px; padding:14px 16px; border:1px solid rgba(128,128,128,.25); height:100%;
}
.badge {
  display:inline-block; padding:2px 10px; border-radius:999px; font-size:.8rem; font-weight:700;
}
.badge-conf { background:#dbeafe; color:#1e3a8a; }
.badge-risk { background:#fee2e2; color:#991b1b; }
.badge-compliant { background:#dcfce7; color:#166534; }
.badge-noncompliant { background:#fee2e2; color:#991b1b; }
.rank1 { border:2px solid #f59e0b !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================ DATA ============================================================
@st.cache_data
def load_tickets() -> pd.DataFrame:
    df = pd.read_csv("data/tickets.csv")
    df["date"] = df["date"].astype(str).str[:10]
    return df


@st.cache_data(show_spinner=False)
def train_status_table(tickets: pd.DataFrame, train: str) -> pd.DataFrame:
    dates = sorted(tickets.loc[tickets.train_id == train, "date"].unique())
    rows = []
    for d in dates:
        seg = aggregate_segments(tickets, train, d)
        top = seg.loc[seg["occupancy"].idxmax()]
        rows.append({
            "date": d, "max_occupancy": top["occupancy"],
            "bottleneck": f"{STATION_NAME[top['from_station']]}–{STATION_NAME[top['to_station']]}",
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def run_pipeline(tickets: pd.DataFrame, train: str, date: str):
    ext = load_external(date)
    seg_df = aggregate_segments(tickets, train, date)
    matrix = build_seat_matrix(tickets, train, date)
    gaps = find_gaps(matrix)
    fc = forecast_demand(tickets, date, ext)
    policies = generate_policies(fc, matrix)
    baseline = run_baseline(fc, matrix)
    sims = {p.name: simulate(p, fc, matrix, n_runs=200) for p in policies}
    ranking = rank_policies(sims)
    return ext, seg_df, matrix, gaps, fc, policies, baseline, sims, ranking


tickets = load_tickets()

# ============================================================ SESSION STATE ============================================================
st.session_state.setdefault("train", "SE3" if "SE3" in TRAINS else TRAINS[0])
st.session_state.setdefault("audit_log", [])
st.session_state.setdefault("selected_policy", "balanced")
st.session_state.setdefault("last_toast", None)

# tìm ngày "sự cố" mạnh nhất của từng tàu để làm mặc định ngày khởi hành
status_by_train = {tr: train_status_table(tickets, tr) for tr in TRAINS}
if "depart_date" not in st.session_state:
    worst = max(status_by_train.items(), key=lambda kv: kv[1]["max_occupancy"].max())
    st.session_state["depart_date"] = worst[1].loc[worst[1]["max_occupancy"].idxmax(), "date"]
    if worst[0] != st.session_state["train"]:
        st.session_state["train"] = worst[0]

# ============================================================ HEADER ============================================================
h1, h2 = st.columns([3, 1])
with h1:
    st.markdown("## 🚆 Vietnam Railway United — Decision Copilot")
    st.caption("Đang đăng nhập: **Chị Hạnh – Trưởng phòng RM**")
with h2:
    st.markdown(
        "<div style='text-align:right;padding-top:18px;color:gray;font-size:.85rem'>"
        "Tuyến trục Hà Nội – Sài Gòn · Decision Demo (không phải hệ thống thật)</div>",
        unsafe_allow_html=True,
    )

hc1, hc2, hc3 = st.columns(3)
with hc1:
    st.selectbox("Tuyến", ["Hà Nội – Sài Gòn (8 ga)"], index=0, disabled=True)
with hc2:
    st.selectbox("Chuyến tàu", TRAINS, key="train")
with hc3:
    avail_dates = sorted(tickets.loc[tickets.train_id == st.session_state["train"], "date"].unique())
    if st.session_state["depart_date"] not in avail_dates:
        st.session_state["depart_date"] = avail_dates[-1]
    st.selectbox("Ngày khởi hành", avail_dates, key="depart_date")

train = st.session_state["train"]
depart_date = st.session_state["depart_date"]

st.divider()

ext, seg_df, matrix, gaps, fc, policies, baseline, sims, ranking = run_pipeline(tickets, train, depart_date)
policy_map = {p.name: p for p in policies}

# ============================================================ LEFT: EXCEPTION FEED + HEATMAP ============================================================
left, center = st.columns([1, 2])

with left:
    st.markdown("#### 🚨 Exception Alert Feed")
    for tr in TRAINS:
        stat = status_by_train[tr]
        row = stat.loc[stat["date"] == depart_date] if depart_date in stat["date"].values else stat.iloc[[-1]]
        occ = float(row["max_occupancy"].iloc[0])
        bott = row["bottleneck"].iloc[0]
        is_alert = occ >= 0.90
        css_class = "alert-row-blink" if is_alert else "alert-row-ok"
        label = f"{'🔴' if is_alert else '🟢'} {tr} — {bott} {fmt_pct(occ,0)}" + (" — SỰ CỐ QUỸ GHẾ" if is_alert else "")
        st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
        if st.button(label, key=f"alert_{tr}", width="stretch"):
            st.session_state["train"] = tr
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f"#### 🗺️ Heatmap tải theo chặng — {train} · {depart_date}")
    seg_labels = [f"{STATION_NAME[r.from_station]}→{STATION_NAME[r.to_station]}" for r in seg_df.itertuples()]
    fig_seg = go.Figure(data=go.Heatmap(
        z=[seg_df["occupancy"].tolist()],
        x=seg_labels, y=["Tỉ lệ lấp đầy"],
        colorscale=[[0, "#bbf7d0"], [0.7, "#fde68a"], [1, "#dc2626"]],
        zmin=0, zmax=1,
        text=[[fmt_pct(v, 0) for v in seg_df["occupancy"]]],
        texttemplate="%{text}", showscale=False,
    ))
    fig_seg.update_layout(height=140, margin=dict(l=4, r=4, t=4, b=4))
    st.plotly_chart(fig_seg, width="stretch", config={"displayModeBar": False})

    seg_ids = list(seg_df["segment_id"])
    coach_occ = matrix.groupby("coach")[seg_ids].apply(lambda d: (d == "SOLD").mean())
    fig_coach = go.Figure(data=go.Heatmap(
        z=coach_occ.values, x=seg_labels, y=[f"Toa {c}" for c in coach_occ.index],
        colorscale=[[0, "#bbf7d0"], [0.7, "#fde68a"], [1, "#dc2626"]], zmin=0, zmax=1,
        text=[[fmt_pct(v, 0) for v in row] for row in coach_occ.values], texttemplate="%{text}",
        colorbar=dict(title="Lấp đầy"),
    ))
    fig_coach.update_layout(height=340, margin=dict(l=4, r=4, t=10, b=4))
    st.caption("Ô đỏ = cháy vé · Ô xanh nhạt = chặng khuyến mãi (theo toa)")
    st.plotly_chart(fig_coach, width="stretch", config={"displayModeBar": False})

# ============================================================ CENTER: 3 POLICY CARDS + RANKING ============================================================
with center:
    st.markdown("#### 📋 3 Chính sách đề xuất (so với Baseline Bán-ngay)")
    cards = st.columns(3)
    rank_by_policy = dict(zip(ranking["policy"], ranking["rank"]))

    for col, pname in zip(cards, POLICY_ORDER):
        p = policy_map[pname]
        sim = sims[pname]
        rk = rank_by_policy.get(pname, 3)
        delta_pct = (sim["revenue"] - baseline["revenue"]) / baseline["revenue"] if baseline["revenue"] else 0
        with col:
            card_class = "policy-card rank1" if rk == 1 else "policy-card"
            st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
            crown = " 🏆" if rk == 1 else ""
            st.markdown(f"**{p.label_vi}{crown}**  \n`#{rk}`")
            st.metric("Doanh thu kỳ vọng", fmt_vnd(sim["revenue"]), f"{delta_pct*100:+.1f}% vs baseline")
            st.write(f"Lấp đầy: **{fmt_pct(sim['occupancy'],1)}** · Pax-km: **{sim['pax_km']:,.0f}**")
            st.write(
                f"<span class='badge badge-conf'>Tin cậy {fmt_pct(sim['confidence'],0)}</span> "
                f"<span class='badge badge-risk'>Rủi ro {fmt_vnd(sim['risk'])}</span>",
                unsafe_allow_html=True,
            )
            st.caption("💡 " + {
                "conservative": "Hợp lúc: ngày thường, cầu thấp, cần chắc chắn.",
                "balanced": "Hợp lúc: vận hành thông thường, cân bằng rủi ro.",
                "aggressive": "Hợp lúc: cao điểm lễ/Tết, cầu vượt cung.",
            }[pname])
            if st.button(f"Chọn để xem giải thích", key=f"select_{pname}", width="stretch"):
                st.session_state["selected_policy"] = pname
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("##### Bảng xếp hạng")
    show_rank = ranking.copy()
    show_rank["revenue"] = show_rank["revenue"].map(fmt_vnd)
    show_rank["occupancy"] = show_rank["occupancy"].map(lambda v: fmt_pct(v, 1))
    show_rank["risk"] = show_rank["risk"].map(fmt_vnd)
    show_rank["confidence"] = show_rank["confidence"].map(lambda v: fmt_pct(v, 0))
    show_rank["pax_km"] = show_rank["pax_km"].map(lambda v: f"{v:,.0f}")
    st.dataframe(show_rank[["rank", "policy", "revenue", "occupancy", "pax_km", "risk", "confidence"]],
                 hide_index=True, width="stretch")

st.divider()

# ============================================================ EXPLAINABILITY + GAP LIST ============================================================
exp_col, gap_col = st.columns([3, 2])

selected_name = st.session_state["selected_policy"]
selected_policy = policy_map[selected_name]
selected_sim = sims[selected_name]
explanation = explain(selected_policy, selected_sim, baseline, fc)

with exp_col:
    st.markdown(f"#### 🔎 Explainability Panel — {selected_policy.label_vi}")
    conf_val = explanation["confidence"]["value"]
    compliant_badge = "badge-compliant" if explanation["compliant"] else "badge-noncompliant"
    st.markdown(
        f"<span class='badge badge-conf'>{explanation['confidence']['label']}</span> "
        f"<span class='badge {compliant_badge}'>{explanation['compliance']}</span>",
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown(f"**What (Làm gì):** {explanation['what']}")
    st.markdown(f"**Why (Vì sao):** {explanation['why']}")
    st.markdown(f"**Benefit vs Baseline:** {explanation['benefit_vs_baseline']}")
    st.markdown(f"**⚠️ Rủi ro:** {explanation['risk']}")
    st.markdown(f"**Phù hợp khi:** {explanation['policy_fit']}")

with gap_col:
    st.markdown(f"#### 🧩 Gap Engine — AI tìm được {len(gaps)} khoảng ghép được")
    if len(gaps):
        top_gap = gaps.iloc[0]
        st.info(
            f"VD: Ghế {top_gap['seat_id'].split('-')[-1]}, toa {top_gap['coach']}, "
            f"chặng {STATION_NAME[top_gap['gap_from']]}–{STATION_NAME[top_gap['gap_to']]}, "
            f"+{fmt_vnd(top_gap['extra_revenue'])}"
        )
        show_gaps = gaps.copy()
        show_gaps["seat"] = show_gaps["seat_id"] + " (toa " + show_gaps["coach"].astype(str) + ")"
        show_gaps["chặng"] = show_gaps["gap_from"].map(STATION_NAME) + "–" + show_gaps["gap_to"].map(STATION_NAME)
        show_gaps["+doanh thu"] = show_gaps["extra_revenue"].map(fmt_vnd)
        show_gaps["khớp cầu"] = show_gaps["matched_demand"].map(lambda v: fmt_pct(v, 0))
        st.dataframe(show_gaps[["seat", "chặng", "khớp cầu", "+doanh thu"]], hide_index=True,
                     width="stretch", height=260)
    else:
        st.write("Không tìm thấy khoảng ghép được cho chuyến/ngày này.")

st.divider()

# ============================================================ APPROVE / OVERRIDE ============================================================
st.markdown(f"### ✅ Quyết định cho: {selected_policy.label_vi} — {train} · {depart_date}")

if st.session_state["last_toast"]:
    st.success(st.session_state["last_toast"])

btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    if st.button("✅ APPROVE — Duyệt chính sách", key="approve_btn", width="stretch"):
        st.session_state["audit_log"].append({
            "timestamp": dt.datetime.now().isoformat(sep=" ", timespec="seconds"),
            "train": train, "date": depart_date, "policy": selected_policy.label_vi,
            "action": "APPROVE", "reason": "-",
        })
        msg = "Đã cập nhật chính sách vào hệ thống dsvn.vn thành công."
        st.session_state["last_toast"] = msg
        st.toast(msg, icon="✅")
        st.rerun()

with btn_col2:
    if st.button("🔴 OVERRIDE — Từ chối, chọn lý do", key="override_btn", width="stretch"):
        st.session_state["show_override_dialog"] = True


@st.dialog("Lý do Override")
def override_dialog():
    st.write(f"Override chính sách **{selected_policy.label_vi}** cho **{train} · {depart_date}**.")
    reason = st.selectbox(
        "Lý do (bắt buộc chọn)", OVERRIDE_REASONS, index=None,
        placeholder="-- Chọn lý do --", key="override_reason",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Xác nhận Override", type="primary", width="stretch", disabled=(reason is None)):
            st.session_state["audit_log"].append({
                "timestamp": dt.datetime.now().isoformat(sep=" ", timespec="seconds"),
                "train": train, "date": depart_date, "policy": selected_policy.label_vi,
                "action": "OVERRIDE", "reason": reason,
            })
            st.session_state["last_toast"] = f"Đã ghi nhận OVERRIDE — lý do: {reason}."
            st.session_state["show_override_dialog"] = False
            st.rerun()
    with c2:
        if st.button("Huỷ", width="stretch"):
            st.session_state["show_override_dialog"] = False
            st.rerun()


if st.session_state.get("show_override_dialog"):
    override_dialog()

# ============================================================ AUDIT LOG ============================================================
with st.expander(f"📜 Audit Log ({len(st.session_state['audit_log'])} bản ghi)", expanded=False):
    if st.session_state["audit_log"]:
        st.dataframe(pd.DataFrame(st.session_state["audit_log"])[::-1], hide_index=True, width="stretch")
    else:
        st.caption("Chưa có quyết định nào trong phiên này.")
