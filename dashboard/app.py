import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import numpy as np

st.set_page_config(page_title="마케팅 대시보드", page_icon="📊", layout="wide")

st.markdown("""
<style>
/* KPI 카드 */
[data-testid="stMetricValue"] { font-size: 1.15rem !important; font-weight: 600; color: #1a1a2e; }
[data-testid="stMetricLabel"] { font-size: 0.75rem !important; color: #6b7280; letter-spacing: .03em; }
[data-testid="stMetricDelta"] { font-size: 0.72rem !important; }
[data-testid="metric-container"] {
    background: #f8f9fc; border-radius: 10px; padding: 12px 16px;
    border: 1px solid #e5e7eb; }

/* 사이드바 태그 */
section[data-testid="stSidebar"] .stMultiSelect:nth-of-type(1) [data-baseweb="tag"] {
    background-color: #4F46E5 !important; border-radius: 6px; }
section[data-testid="stSidebar"] .stMultiSelect:nth-of-type(2) [data-baseweb="tag"] {
    background-color: #7C3AED !important; border-radius: 6px; }
section[data-testid="stSidebar"] [data-baseweb="tag"] span { color: #fff !important; }
section[data-testid="stSidebar"] [data-baseweb="select"] > div:focus-within {
    border-color: #4F46E5 !important; box-shadow: 0 0 0 1px #4F46E5 !important; }

/* 탭 */
[data-testid="stTab"] { font-size: 0.85rem; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

# ── 공통 색상 팔레트 ─────────────────────────────────────────
CHANNEL_COLOR = {"구글": "#4285F4", "메타": "#1877F2", "네이버": "#03C75A"}
PALETTE       = ["#4F46E5", "#7C3AED", "#EC4899", "#F59E0B", "#10B981", "#06B6D4"]
CHART_LAYOUT  = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Pretendard, Apple SD Gothic Neo, sans-serif", color="#374151"),
    margin=dict(t=40, b=30, l=10, r=10),
    xaxis=dict(showgrid=False, linecolor="#e5e7eb"),
    yaxis=dict(gridcolor="#f3f4f6", linecolor="#e5e7eb"),
)

def apply_layout(fig, **extra):
    fig.update_layout(**{**CHART_LAYOUT, **extra})
    return fig

BASE_DIR = Path(__file__).parent.parent
CH_DIR   = BASE_DIR / "data" / "raw" / "channel"
AF_DIR   = BASE_DIR / "data" / "raw" / "appsflyer"
BG_DIR   = BASE_DIR / "data" / "raw" / "budget"

# ── 데이터 로더 ───────────────────────────────────────────────
@st.cache_data
def load_data():
    af_frames, ch_frames = [], []
    for f in sorted(AF_DIR.glob("*.parquet")):
        af_frames.append(pd.read_parquet(f))
    for f in sorted(AF_DIR.glob("*.csv")):
        if not (AF_DIR / (f.stem + ".parquet")).exists():
            af_frames.append(pd.read_csv(f))
    for f in sorted(CH_DIR.glob("*.parquet")):
        ch_frames.append(pd.read_parquet(f))
    for f in sorted(CH_DIR.glob("*.csv")):
        if not (CH_DIR / (f.stem + ".parquet")).exists():
            ch_frames.append(pd.read_csv(f))
    if not af_frames or not ch_frames:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    af_raw = pd.concat(af_frames, ignore_index=True)
    ch_raw = pd.concat(ch_frames, ignore_index=True)

    af = af_raw.rename(columns={
        "일": "date", "미디어소스": "source", "캠페인": "campaign",
        "그룹": "adgroup", "소재": "creative",
        "클릭": "af_click", "회원가입": "af_reg",
        "구매": "af_purchase", "구매매출": "af_revenue"
    })
    ch = ch_raw.rename(columns={
        "일": "date", "채널": "channel", "채널분류": "channel_type",
        "캠페인": "campaign", "캠페인목적": "campaign_goal",
        "그룹": "adgroup", "소재": "creative",
        "노출": "impression", "클릭": "click", "비용": "cost",
        "회원가입": "reg", "구매": "purchase", "구매매출": "revenue"
    })
    source_map = {"googleadwords_int": "구글", "Facebook Ads": "메타", "naver_search": "네이버"}
    af["channel"] = af["source"].map(source_map).fillna(af["source"])

    merged = pd.merge(
        ch,
        af[["channel","campaign","adgroup","creative","af_click","af_reg","af_purchase","af_revenue"]],
        on=["channel","campaign","adgroup","creative"], how="left"
    )
    merged["date"] = pd.to_datetime(merged["date"])
    merged["creative_type"] = merged["creative"].str.extract(r"^([A-Z]+)_")

    def safe_div(a, b): return a / b.replace(0, np.nan)
    merged["ctr"]      = safe_div(merged["click"],    merged["impression"])
    merged["cpc"]      = safe_div(merged["cost"],     merged["click"])
    merged["cvr"]      = safe_div(merged["purchase"], merged["click"])
    merged["roas_pct"] = safe_div(merged["revenue"],  merged["cost"]) * 100
    merged["cpa"]      = safe_div(merged["cost"],     merged["purchase"])
    merged["cpr"]      = safe_div(merged["cost"],     merged["reg"])
    return merged, af_raw, ch_raw


@st.cache_data
def load_budget():
    files = sorted(BG_DIR.glob("*_budget.csv"))
    if not files:
        return None
    return pd.read_csv(files[-1])


def detect_flags(df):
    flags = []
    if df.empty:
        return pd.DataFrame()
    last_date = df["date"].max()
    today = df[df["date"] == last_date].copy()
    today["roas_pct"] = today["revenue"] / today["cost"].replace(0, np.nan) * 100
    today["cpa"]      = today["cost"] / today["purchase"].replace(0, np.nan)
    ch_avg_cpa = today.groupby("channel")["cpa"].mean()

    for _, row in today.iterrows():
        if pd.notna(row["roas_pct"]) and row["roas_pct"] < 100:
            flags.append({"심각도": "🔴 즉시점검", "채널": row["channel"],
                "캠페인": row["campaign"], "소재": row["creative"],
                "지표": "ROAS", "지표값": f"{row['roas_pct']:.1f}%", "기준값": "100%"})
        avg = ch_avg_cpa.get(row["channel"], np.nan)
        if pd.notna(row["cpa"]) and pd.notna(avg) and row["cpa"] > avg * 3:
            flags.append({"심각도": "🟡 주의", "채널": row["channel"],
                "캠페인": row["campaign"], "소재": row["creative"],
                "지표": "CPA", "지표값": f"₩{row['cpa']:,.0f}", "기준값": f"₩{avg*3:,.0f}"})

    dates = sorted(df["date"].unique())
    if len(dates) >= 2:
        prev_date = dates[-2]
        prev = df[df["date"] == prev_date].groupby("channel")["cost"].sum()
        curr = today.groupby("channel")["cost"].sum()
        for ch in curr.index:
            if ch in prev.index and prev[ch] > 0:
                delta_pct = (curr[ch] - prev[ch]) / prev[ch] * 100
                if abs(delta_pct) >= 30:
                    flags.append({"심각도": "🟡 주의", "채널": ch,
                        "캠페인": "-", "소재": "-",
                        "지표": "비용증감", "지표값": f"{delta_pct:+.1f}%", "기준값": "±30%"})
    return pd.DataFrame(flags)


# ── 데이터 로드 ───────────────────────────────────────────────
df, af_raw, ch_raw = load_data()
if df.empty:
    st.error("CSV/Parquet 파일을 찾을 수 없습니다.")
    st.stop()

# ── 사이드바 필터 ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 필터")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()
    all_channels  = sorted(df["channel"].dropna().unique())
    sel_channel   = st.multiselect("채널", all_channels, default=all_channels)
    all_campaigns = sorted(df["campaign"].dropna().unique())
    sel_campaign  = st.multiselect("캠페인", all_campaigns, default=all_campaigns)
    date_min, date_max = df["date"].min().date(), df["date"].max().date()
    sel_dates = st.date_input("날짜 범위", [date_min, date_max])

filt = df.copy()
if sel_channel:  filt = filt[filt["channel"].isin(sel_channel)]
if sel_campaign: filt = filt[filt["campaign"].isin(sel_campaign)]
if len(sel_dates) == 2:
    filt = filt[(filt["date"] >= pd.Timestamp(sel_dates[0])) &
                (filt["date"] <= pd.Timestamp(sel_dates[1]))]

# ── 탭 ───────────────────────────────────────────────────────
tab_daily, tab_ov, tab_cr, tab_eda, tab_raw_tab = st.tabs(
    ["🔴 Daily Check", "📊 성과 Overview", "🎨 소재 분석", "🔬 EDA", "📋 원본 데이터"]
)

# ════════════════════════════════════════════════════════════
# TAB 1 · Daily Check
# ════════════════════════════════════════════════════════════
with tab_daily:

    # 예산 소진 게이지
    st.subheader("💰 예산 소진 현황")
    budget_df = load_budget()
    if budget_df is None:
        st.info("예산 파일 없음. `data/raw/budget/YYYY-MM-DD_budget.csv` 를 추가하세요.")
    else:
        last_date = filt["date"].max()
        daily_cost = (filt[filt["date"] == last_date]
                      .groupby("channel")["cost"].sum().reset_index()
                      .rename(columns={"channel": "채널", "cost": "실제비용"}))
        mb = pd.merge(budget_df, daily_cost, on="채널", how="left").fillna(0)
        mb["소진율"] = mb["실제비용"] / mb["일예산"] * 100

        cols = st.columns(len(mb))
        for i, row in mb.iterrows():
            pct   = min(row["소진율"], 100)
            color = "#EF4444" if pct >= 80 else "#F59E0B" if pct >= 60 else "#10B981"
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct,
                number={"suffix": "%", "font": {"size": 26, "color": "#1a1a2e"}},
                title={"text": row["채널"], "font": {"size": 15, "color": "#6b7280"}},
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": "#d1d5db"},
                    "bar":  {"color": color},
                    "bgcolor": "#f9fafb",
                    "bordercolor": "#e5e7eb",
                    "steps": [
                        {"range": [0,  60], "color": "#f0fdf4"},
                        {"range": [60, 80], "color": "#fffbeb"},
                        {"range": [80,100], "color": "#fef2f2"},
                    ],
                },
            ))
            fig_g.update_layout(height=200, margin=dict(t=40, b=0, l=20, r=20),
                                paper_bgcolor="rgba(0,0,0,0)")
            with cols[i]:
                st.plotly_chart(fig_g, use_container_width=True)
                st.caption(f"₩{row['실제비용']:,.0f} / ₩{row['일예산']:,.0f} ({row['소진율']:.1f}%)")

    st.divider()

    # 이상치 플래그
    st.subheader("🚨 이상치 플래그")
    flag_df = detect_flags(filt)
    if flag_df.empty:
        st.success("✅ 이상 없음")
    else:
        st.dataframe(flag_df, use_container_width=True, hide_index=True)

    st.divider()

    # 전일 비용 증감
    st.subheader("📉 전일 비용 증감")
    dates_sorted = sorted(filt["date"].unique())
    if len(dates_sorted) < 2:
        st.info("전전일 데이터 없음 — 데이터가 2일 이상일 때 표시됩니다.")
    else:
        last, prev = dates_sorted[-1], dates_sorted[-2]
        curr_cost = filt[filt["date"] == last].groupby("channel")["cost"].sum()
        prev_cost = filt[filt["date"] == prev].groupby("channel")["cost"].sum()
        dcols = st.columns(len(curr_cost))
        for i, ch in enumerate(curr_cost.index):
            c_val = curr_cost[ch]
            p_val = prev_cost.get(ch, 0)
            delta = (c_val - p_val) / p_val * 100 if p_val else 0
            with dcols[i]:
                st.metric(label=ch, value=f"₩{c_val:,.0f}",
                          delta=f"{delta:+.1f}%", delta_color="inverse")

# ════════════════════════════════════════════════════════════
# TAB 2 · 성과 Overview
# ════════════════════════════════════════════════════════════
with tab_ov:
    st.subheader("핵심 KPI")
    total = {k: filt[k].sum() for k in ["impression","click","cost","revenue","purchase","reg"]}
    roas_t = total["revenue"] / total["cost"] * 100 if total["cost"] else 0
    cpa_t  = total["cost"] / total["purchase"] if total["purchase"] else 0
    ctr_t  = total["click"] / total["impression"] if total["impression"] else 0

    c1,c2,c3,c4,c5,c6,c7,c8 = st.columns(8)
    c1.metric("노출",  f'{total["impression"]:,.0f}')
    c2.metric("클릭",  f'{total["click"]:,.0f}')
    c3.metric("CTR",  f'{ctr_t:.2%}')
    c4.metric("비용",  f'₩{total["cost"]:,.0f}')
    c5.metric("매출",  f'₩{total["revenue"]:,.0f}')
    c6.metric("ROAS", f'{roas_t:.1f}%')
    c7.metric("구매",  f'{total["purchase"]:,.0f}')
    c8.metric("CPA",  f'₩{cpa_t:,.0f}')
    st.divider()

    daily = filt.groupby("date").agg(
        cost=("cost","sum"), revenue=("revenue","sum"),
        click=("click","sum"), purchase=("purchase","sum")
    ).reset_index()
    daily["roas_pct"] = daily["revenue"] / daily["cost"].replace(0, np.nan) * 100

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("일별 매출 / 비용")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily["date"], y=daily["revenue"], name="매출", marker_color="#4F46E5"))
        fig.add_trace(go.Bar(x=daily["date"], y=daily["cost"],    name="비용", marker_color="#A5B4FC"))
        apply_layout(fig, barmode="group", yaxis_title="금액 (₩)")
        st.plotly_chart(fig, use_container_width=True)
    with col_r:
        st.subheader("일별 ROAS 추이 (%)")
        fig2 = px.line(daily, x="date", y="roas_pct", markers=True,
                       color_discrete_sequence=["#4F46E5"],
                       labels={"roas_pct":"ROAS (%)","date":"날짜"})
        fig2.add_hline(y=100, line_dash="dash", line_color="#EF4444",
                       annotation_text="ROAS 100%", annotation_font_color="#EF4444")
        apply_layout(fig2, yaxis_ticksuffix="%")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("채널 × 캠페인목적 ROAS 히트맵 (%)")
    pivot = filt.groupby(["channel","campaign_goal"]).apply(
        lambda x: x["revenue"].sum() / x["cost"].sum() * 100 if x["cost"].sum() else np.nan
    ).reset_index(name="roas_pct")
    heat = pivot.pivot(index="channel", columns="campaign_goal", values="roas_pct")
    fig3 = px.imshow(heat, text_auto=".1f", color_continuous_scale="Blues",
                     labels=dict(color="ROAS (%)"), aspect="auto")
    apply_layout(fig3)
    st.plotly_chart(fig3, use_container_width=True)

    ch_agg = filt.groupby("channel").agg(
        cost=("cost","sum"), revenue=("revenue","sum"),
        click=("click","sum"), impression=("impression","sum"),
        purchase=("purchase","sum"), reg=("reg","sum")
    ).reset_index()
    ch_agg["roas_pct"] = ch_agg["revenue"] / ch_agg["cost"].replace(0,np.nan) * 100
    ch_agg["cpa"]      = ch_agg["cost"]    / ch_agg["purchase"].replace(0,np.nan)
    ch_agg["ctr"]      = ch_agg["click"]   / ch_agg["impression"].replace(0,np.nan)
    ch_agg["color"]    = ch_agg["channel"].map(CHANNEL_COLOR)

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.subheader("채널별 ROAS (%)")
        fig4 = px.bar(ch_agg.sort_values("roas_pct", ascending=False),
                      x="channel", y="roas_pct", color="channel",
                      color_discrete_map=CHANNEL_COLOR,
                      labels={"roas_pct":"ROAS (%)","channel":"채널"})
        fig4.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
        apply_layout(fig4, yaxis_ticksuffix="%", showlegend=False)
        st.plotly_chart(fig4, use_container_width=True)
    with col_r2:
        st.subheader("채널별 비용 비중")
        fig5 = px.pie(ch_agg, names="channel", values="cost", hole=0.45,
                      color="channel", color_discrete_map=CHANNEL_COLOR)
        fig5.update_traces(textfont_size=13)
        apply_layout(fig5)
        st.plotly_chart(fig5, use_container_width=True)

    st.subheader("캠페인별 ROAS 랭킹 (%)")
    cmp_agg = filt.groupby(["channel","campaign"]).agg(
        cost=("cost","sum"), revenue=("revenue","sum"), purchase=("purchase","sum")
    ).reset_index()
    cmp_agg["roas_pct"] = cmp_agg["revenue"] / cmp_agg["cost"].replace(0,np.nan) * 100
    fig6 = px.bar(cmp_agg.sort_values("roas_pct", ascending=False),
                  x="campaign", y="roas_pct", color="channel",
                  color_discrete_map=CHANNEL_COLOR,
                  labels={"roas_pct":"ROAS (%)","campaign":"캠페인"})
    fig6.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
    apply_layout(fig6, yaxis_ticksuffix="%")
    fig6.update_xaxes(tickangle=30)
    st.plotly_chart(fig6, use_container_width=True)

# ════════════════════════════════════════════════════════════
# TAB 3 · 소재 분석
# ════════════════════════════════════════════════════════════
with tab_cr:
    cr_agg = filt.groupby(["creative_type","channel"]).agg(
        impression=("impression","sum"), click=("click","sum"),
        cost=("cost","sum"), revenue=("revenue","sum"), purchase=("purchase","sum")
    ).reset_index()
    cr_agg["ctr"]      = cr_agg["click"]   / cr_agg["impression"].replace(0,np.nan)
    cr_agg["roas_pct"] = cr_agg["revenue"] / cr_agg["cost"].replace(0,np.nan) * 100
    cr_agg["cpa"]      = cr_agg["cost"]    / cr_agg["purchase"].replace(0,np.nan)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("소재 유형별 CTR")
        ctr_by_type = (cr_agg.groupby("creative_type")
                       .apply(lambda x: pd.Series({"ctr": x["click"].sum()/x["impression"].sum()}))
                       .reset_index())
        fig7 = px.bar(ctr_by_type, x="creative_type", y="ctr",
                      color="creative_type", color_discrete_sequence=PALETTE,
                      labels={"creative_type":"소재 유형","ctr":"CTR"})
        fig7.update_traces(texttemplate="%{y:.2%}", textposition="outside")
        apply_layout(fig7, showlegend=False)
        st.plotly_chart(fig7, use_container_width=True)
    with c2:
        st.subheader("소재 유형 × 채널 ROAS 히트맵 (%)")
        heat2 = cr_agg.pivot_table(index="creative_type", columns="channel", values="roas_pct")
        fig8  = px.imshow(heat2, text_auto=".1f", color_continuous_scale="Blues",
                          labels=dict(color="ROAS (%)"), aspect="auto")
        apply_layout(fig8)
        st.plotly_chart(fig8, use_container_width=True)

    # 메시지 카테고리별 ROAS
    st.subheader("메시지 카테고리별 ROAS (%)")
    filt_cr = filt.copy()
    filt_cr["msg_category"] = filt_cr["creative"].str.extract(r"^[A-Z]+_([^_]+)_")
    msg_agg = filt_cr.groupby("msg_category").agg(
        cost=("cost","sum"), revenue=("revenue","sum"), purchase=("purchase","sum")
    ).reset_index()
    msg_agg["roas_pct"] = msg_agg["revenue"] / msg_agg["cost"].replace(0, np.nan) * 100
    fig_msg = px.bar(msg_agg.sort_values("roas_pct", ascending=False),
                     x="msg_category", y="roas_pct", color="msg_category",
                     color_discrete_sequence=PALETTE,
                     labels={"msg_category":"메시지","roas_pct":"ROAS (%)"})
    fig_msg.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
    apply_layout(fig_msg, yaxis_ticksuffix="%", showlegend=False)
    st.plotly_chart(fig_msg, use_container_width=True)

    st.subheader("소재별 상세 성과 테이블")
    cr_detail = filt.groupby(["channel","campaign","adgroup","creative","creative_type"]).agg(
        impression=("impression","sum"), click=("click","sum"),
        cost=("cost","sum"), revenue=("revenue","sum"), purchase=("purchase","sum")
    ).reset_index()
    cr_detail["CTR"]  = (cr_detail["click"]   / cr_detail["impression"].replace(0,np.nan)).map("{:.2%}".format)
    cr_detail["CPC"]  = (cr_detail["cost"]    / cr_detail["click"].replace(0,np.nan)).map("₩{:,.0f}".format)
    cr_detail["ROAS"] = (cr_detail["revenue"] / cr_detail["cost"].replace(0,np.nan) * 100).map("{:.1f}%".format)
    cr_detail["CPA"]  = (cr_detail["cost"]    / cr_detail["purchase"].replace(0,np.nan)).map("₩{:,.0f}".format)
    st.dataframe(cr_detail, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════
# TAB 4 · EDA
# ════════════════════════════════════════════════════════════
with tab_eda:
    st.subheader("🔬 탐색적 데이터 분석 (EDA)")

    with st.expander("📐 데이터 개요", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("총 행 수", f"{len(filt):,}")
        c2.metric("날짜 수",  f"{filt['date'].nunique()}")
        c3.metric("소재 수",  f"{filt['creative'].nunique()}")
        missing = filt.isnull().sum().reset_index()
        missing.columns = ["컬럼","결측 수"]
        missing["결측률"] = (missing["결측 수"] / len(filt)).map("{:.1%}".format)
        if missing["결측 수"].sum() == 0:
            st.success("결측치 없음 ✅")
        else:
            st.dataframe(missing[missing["결측 수"] > 0], hide_index=True)

    with st.expander("📊 기술통계", expanded=True):
        num_cols = ["impression","click","cost","revenue","purchase","reg","ctr","roas_pct","cpa","cpc"]
        st.dataframe(filt[num_cols].describe().T.style.format("{:.2f}"), use_container_width=True)

    st.subheader("분포 분석")
    col_sel = st.selectbox("지표 선택", ["roas_pct","ctr","cpa","cpc","cost","revenue","click","impression"])
    by_sel  = st.radio("그룹 기준", ["channel","creative_type","campaign_goal"], horizontal=True)

    c1, c2 = st.columns(2)
    with c1:
        fig_box = px.box(filt, x=by_sel, y=col_sel, color=by_sel,
                         color_discrete_sequence=PALETTE,
                         points="outliers", title=f"{col_sel} 분포 (박스플롯)")
        apply_layout(fig_box)
        st.plotly_chart(fig_box, use_container_width=True)
    with c2:
        fig_vio = px.violin(filt, x=by_sel, y=col_sel, color=by_sel,
                            color_discrete_sequence=PALETTE,
                            box=True, title=f"{col_sel} 분포 (바이올린)")
        apply_layout(fig_vio)
        st.plotly_chart(fig_vio, use_container_width=True)

    st.subheader("지표 간 상관관계")
    corr_cols = ["impression","click","cost","revenue","purchase","reg","roas_pct","ctr","cpa"]
    corr = filt[corr_cols].corr()
    fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale="Blues",
                         aspect="auto")
    apply_layout(fig_corr)
    st.plotly_chart(fig_corr, use_container_width=True)

    st.subheader("지표 산점도")
    c1, c2 = st.columns(2)
    with c1: x_ax = st.selectbox("X축", corr_cols, index=2)
    with c2: y_ax = st.selectbox("Y축", corr_cols, index=3)
    fig_sc = px.scatter(filt, x=x_ax, y=y_ax, color="channel",
                        color_discrete_map=CHANNEL_COLOR,
                        hover_data=["campaign","creative"])
    apply_layout(fig_sc)
    st.plotly_chart(fig_sc, use_container_width=True)

    st.subheader("이상치 탐지 (IQR)")
    out_col  = st.selectbox("이상치 확인할 지표", ["roas_pct","cpa","ctr","cost","revenue"], key="out")
    q1, q3   = filt[out_col].quantile(0.25), filt[out_col].quantile(0.75)
    iqr      = q3 - q1
    outliers = filt[(filt[out_col] < q1 - 1.5*iqr) | (filt[out_col] > q3 + 1.5*iqr)]
    st.write(f"**{out_col}** 이상치: {len(outliers)}행 (전체의 {len(outliers)/len(filt):.1%})")
    if not outliers.empty:
        st.dataframe(outliers[["date","channel","campaign","creative",out_col]]
                     .sort_values(out_col, ascending=False),
                     use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════
# TAB 5 · 원본 데이터
# ════════════════════════════════════════════════════════════
with tab_raw_tab:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Channel 원본")
        st.dataframe(ch_raw, use_container_width=True)
    with c2:
        st.subheader("AppsFlyer 원본")
        st.dataframe(af_raw, use_container_width=True)
    st.subheader("조인된 데이터")
    st.dataframe(filt, use_container_width=True)
    csv = filt.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ CSV 다운로드", csv, "joined_data.csv", "text/csv")
