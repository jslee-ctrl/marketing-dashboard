# 대시보드 재설계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 퍼마 팀 일별 워크플로우(예산→성과→드릴다운)에 맞게 대시보드를 5탭으로 재구성하고 Daily Check 탭을 신규 추가한다.

**Architecture:** `dashboard/app.py` 단일 파일을 전면 재작성한다. 데이터 로더(`load_data`, `load_budget`)를 파일 상단에 분리하고, 탭별 렌더링 로직을 순서대로 배치한다. 예산 파일은 `data/raw/budget/YYYY-MM-DD_budget.csv`에서 가장 최신 파일을 자동으로 읽는다.

**Tech Stack:** Python 3.x, Streamlit 1.58, Pandas, Plotly Express, Plotly Graph Objects

## Global Constraints

- ROAS 단위: % (revenue / cost × 100). 배수(x) 표기 금지.
- 금액 포맷: ₩{:,.0f}
- 탭 순서 고정: Daily Check → 성과 Overview → 소재 분석 → EDA → 원본 데이터
- parquet 우선, 같은 날 csv+parquet 공존 시 parquet만 읽음
- 데이터 경로: `CH_DIR = BASE_DIR/data/raw/channel`, `AF_DIR = BASE_DIR/data/raw/appsflyer`, `BG_DIR = BASE_DIR/data/raw/budget`

---

### Task 1: 예산 로더 및 폴더 생성

**Files:**
- Modify: `dashboard/app.py` — `load_budget()` 함수 추가, `BG_DIR` 경로 상수 추가
- Create: `data/raw/budget/` 폴더 (샘플 파일 포함)

**Interfaces:**
- Produces: `load_budget() -> pd.DataFrame | None` — 컬럼 `채널(str), 일예산(int)`. 파일 없으면 `None` 반환.

- [ ] **Step 1: 예산 샘플 파일 생성**

`data/raw/budget/2025-01-01_budget.csv` 내용:
```
채널,일예산
구글,8000000
메타,3000000
네이버,1000000
```

- [ ] **Step 2: `app.py` 상단에 BG_DIR 추가**

`BASE_DIR`, `CH_DIR`, `AF_DIR` 선언 바로 아래에 추가:
```python
BG_DIR = BASE_DIR / "data" / "raw" / "budget"
```

- [ ] **Step 3: `load_budget()` 함수 추가**

`load_data()` 함수 바로 아래에 추가:
```python
@st.cache_data
def load_budget():
    files = sorted(BG_DIR.glob("*_budget.csv"))
    if not files:
        return None
    return pd.read_csv(files[-1])  # 가장 최신 파일
```

- [ ] **Step 4: 동작 확인**

터미널에서:
```bash
cd "dashboard"
python -c "
import sys; sys.path.insert(0,'.')
from pathlib import Path
import pandas as pd
BG_DIR = Path('../data/raw/budget')
files = sorted(BG_DIR.glob('*_budget.csv'))
print(files)
df = pd.read_csv(files[-1])
print(df)
"
```
Expected:
```
[PosixPath('../data/raw/budget/2025-01-01_budget.csv')]
   채널    일예산
0  구글  8000000
1  메타  3000000
2 네이버  1000000
```

- [ ] **Step 5: 커밋**
```bash
git add data/raw/budget/2025-01-01_budget.csv dashboard/app.py
git commit -m "feat: add budget loader and sample budget file"
```

---

### Task 2: Daily Check 탭 — 예산 소진 게이지

**Files:**
- Modify: `dashboard/app.py` — 탭 선언부 변경, Daily Check 탭 예산 섹션 구현

**Interfaces:**
- Consumes: `load_budget() -> DataFrame(채널, 일예산)`, `filt DataFrame(channel, cost, date)`
- Produces: 채널별 게이지 차트 + 소진율 텍스트

- [ ] **Step 1: 탭 선언부 변경**

기존:
```python
tab_ov, tab_ch, tab_cmp, tab_cr, tab_eda, tab_raw = st.tabs(
    ["📈 Overview", "📡 채널 분석", "🎯 캠페인 분석", "🎨 소재 분석", "🔬 EDA", "📋 원본 데이터"]
)
```
변경 후:
```python
tab_daily, tab_ov, tab_cr, tab_eda, tab_raw = st.tabs(
    ["🔴 Daily Check", "📊 성과 Overview", "🎨 소재 분석", "🔬 EDA", "📋 원본 데이터"]
)
```

- [ ] **Step 2: 예산 소진 게이지 섹션 구현**

`with tab_daily:` 블록 안에 작성:
```python
with tab_daily:
    st.subheader("💰 예산 소진 현황")
    budget_df = load_budget()

    if budget_df is None:
        st.info("예산 파일 없음. `data/raw/budget/YYYY-MM-DD_budget.csv` 를 추가하세요.")
    else:
        # 전일 비용 집계
        if filt["date"].nunique() >= 1:
            last_date = filt["date"].max()
            daily_cost = (
                filt[filt["date"] == last_date]
                .groupby("channel")["cost"].sum()
                .reset_index()
                .rename(columns={"channel": "채널", "cost": "실제비용"})
            )
            merged_budget = pd.merge(budget_df, daily_cost, on="채널", how="left").fillna(0)
            merged_budget["소진율"] = merged_budget["실제비용"] / merged_budget["일예산"] * 100

            cols = st.columns(len(merged_budget))
            for i, row in merged_budget.iterrows():
                pct = min(row["소진율"], 100)
                color = "#e53935" if pct >= 80 else "#f9a825" if pct >= 60 else "#43a047"
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=pct,
                    number={"suffix": "%", "font": {"size": 28}},
                    title={"text": row["채널"], "font": {"size": 16}},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": color},
                        "steps": [
                            {"range": [0, 60], "color": "#e8f5e9"},
                            {"range": [60, 80], "color": "#fff9c4"},
                            {"range": [80, 100], "color": "#ffebee"},
                        ],
                    },
                ))
                fig_gauge.update_layout(height=220, margin=dict(t=40, b=0, l=20, r=20))
                with cols[i]:
                    st.plotly_chart(fig_gauge, use_container_width=True)
                    st.caption(f"₩{row['실제비용']:,.0f} / ₩{row['일예산']:,.0f} ({row['소진율']:.1f}%)")
```

- [ ] **Step 3: 브라우저에서 확인**

`streamlit run app.py` 후 Daily Check 탭 열어서 게이지 3개(구글/메타/네이버) 렌더링 확인.

- [ ] **Step 4: 커밋**
```bash
git add dashboard/app.py
git commit -m "feat: Daily Check tab - budget gauge"
```

---

### Task 3: Daily Check 탭 — 이상치 플래그

**Files:**
- Modify: `dashboard/app.py` — 이상치 감지 로직 + 플래그 테이블

**Interfaces:**
- Consumes: `filt DataFrame(channel, campaign, creative, cost, revenue, purchase, date)`
- Produces: 플래그 테이블 (심각도, 채널, 캠페인, 소재, 지표값, 기준값)

- [ ] **Step 1: 이상치 감지 함수 작성**

`load_budget()` 바로 아래에 추가:
```python
def detect_flags(df):
    flags = []
    if df.empty:
        return pd.DataFrame()

    last_date = df["date"].max()
    today = df[df["date"] == last_date].copy()
    today["roas_pct"] = today["revenue"] / today["cost"].replace(0, np.nan) * 100
    today["cpa"] = today["cost"] / today["purchase"].replace(0, np.nan)

    # 채널 평균 CPA
    ch_avg_cpa = today.groupby("channel")["cpa"].mean()

    for _, row in today.iterrows():
        # ROAS 미회수
        if pd.notna(row["roas_pct"]) and row["roas_pct"] < 100:
            flags.append({
                "심각도": "🔴 즉시점검", "채널": row["channel"],
                "캠페인": row["campaign"], "소재": row["creative"],
                "지표": "ROAS", "지표값": f"{row['roas_pct']:.1f}%", "기준값": "100%"
            })
        # CPA 이상 (채널 평균 3배 초과)
        avg = ch_avg_cpa.get(row["channel"], np.nan)
        if pd.notna(row["cpa"]) and pd.notna(avg) and row["cpa"] > avg * 3:
            flags.append({
                "심각도": "🟡 주의", "채널": row["channel"],
                "캠페인": row["campaign"], "소재": row["creative"],
                "지표": "CPA", "지표값": f"₩{row['cpa']:,.0f}", "기준값": f"₩{avg*3:,.0f}"
            })

    # 전일 대비 비용 ±30%
    dates = sorted(df["date"].unique())
    if len(dates) >= 2:
        prev_date = dates[-2]
        prev = df[df["date"] == prev_date].groupby("channel")["cost"].sum()
        curr = today.groupby("channel")["cost"].sum()
        for ch in curr.index:
            if ch in prev.index and prev[ch] > 0:
                delta_pct = (curr[ch] - prev[ch]) / prev[ch] * 100
                if abs(delta_pct) >= 30:
                    flags.append({
                        "심각도": "🟡 주의", "채널": ch,
                        "캠페인": "-", "소재": "-",
                        "지표": "비용증감", "지표값": f"{delta_pct:+.1f}%", "기준값": "±30%"
                    })

    return pd.DataFrame(flags)
```

- [ ] **Step 2: Daily Check 탭에 플래그 섹션 추가**

예산 게이지 블록 아래, `with tab_daily:` 안에 추가:
```python
    st.divider()
    st.subheader("🚨 이상치 플래그")
    flag_df = detect_flags(filt)
    if flag_df.empty:
        st.success("✅ 이상 없음")
    else:
        st.dataframe(flag_df, use_container_width=True, hide_index=True)
```

- [ ] **Step 3: 전일 비용 증감 카드 추가**

플래그 섹션 아래에 추가:
```python
    st.divider()
    st.subheader("📉 전일 비용 증감")
    dates = sorted(filt["date"].unique())
    if len(dates) < 2:
        st.info("전전일 데이터 없음 — 데이터가 2일 이상일 때 표시됩니다.")
    else:
        last, prev = dates[-1], dates[-2]
        curr_cost = filt[filt["date"] == last].groupby("channel")["cost"].sum()
        prev_cost = filt[filt["date"] == prev].groupby("channel")["cost"].sum()
        dcols = st.columns(len(curr_cost))
        for i, ch in enumerate(curr_cost.index):
            c_val = curr_cost[ch]
            p_val = prev_cost.get(ch, 0)
            delta = (c_val - p_val) / p_val * 100 if p_val else 0
            with dcols[i]:
                st.metric(
                    label=ch,
                    value=f"₩{c_val:,.0f}",
                    delta=f"{delta:+.1f}%",
                    delta_color="inverse"
                )
```

- [ ] **Step 4: 브라우저에서 확인**

Daily Check 탭에서:
- 게이지 차트 정상 렌더링
- 이상치 플래그 테이블 or ✅ 이상 없음 표시
- 전일 비용 카드 (1일 데이터면 "전전일 없음" 안내)

- [ ] **Step 5: 커밋**
```bash
git add dashboard/app.py
git commit -m "feat: Daily Check tab - anomaly flags and cost delta cards"
```

---

### Task 4: 성과 Overview 탭 재구성

**Files:**
- Modify: `dashboard/app.py` — 기존 Overview + 채널 분석 + 캠페인 분석 탭을 `tab_ov` 하나로 통합

**Interfaces:**
- Consumes: `filt DataFrame`
- Produces: KPI 카드 8개, 일별 차트, 히트맵, 채널별 ROAS/비용, 캠페인 랭킹

- [ ] **Step 1: `with tab_ov:` 블록 전면 교체**

```python
with tab_ov:
    st.subheader("핵심 KPI")
    total = {
        "impression": filt["impression"].sum(),
        "click":      filt["click"].sum(),
        "cost":       filt["cost"].sum(),
        "revenue":    filt["revenue"].sum(),
        "purchase":   filt["purchase"].sum(),
        "reg":        filt["reg"].sum(),
    }
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

    # 일별 추이
    daily = filt.groupby("date").agg(
        cost=("cost","sum"), revenue=("revenue","sum"),
        click=("click","sum"), purchase=("purchase","sum")
    ).reset_index()
    daily["roas_pct"] = daily["revenue"] / daily["cost"].replace(0, np.nan) * 100

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("일별 매출 / 비용")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily["date"], y=daily["revenue"], name="매출", marker_color="#4C78A8"))
        fig.add_trace(go.Bar(x=daily["date"], y=daily["cost"],    name="비용", marker_color="#F58518"))
        fig.update_layout(barmode="group", xaxis_title="날짜", yaxis_title="금액 (₩)")
        st.plotly_chart(fig, use_container_width=True)
    with col_r:
        st.subheader("일별 ROAS 추이 (%)")
        fig2 = px.line(daily, x="date", y="roas_pct", markers=True,
                       labels={"roas_pct":"ROAS (%)","date":"날짜"})
        fig2.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="ROAS=100%")
        fig2.update_layout(yaxis_ticksuffix="%")
        st.plotly_chart(fig2, use_container_width=True)

    # 채널 × 캠페인목적 히트맵
    st.subheader("채널 × 캠페인목적 ROAS 히트맵 (%)")
    pivot = filt.groupby(["channel","campaign_goal"]).apply(
        lambda x: x["revenue"].sum() / x["cost"].sum() * 100 if x["cost"].sum() else np.nan
    ).reset_index(name="roas_pct")
    heat = pivot.pivot(index="channel", columns="campaign_goal", values="roas_pct")
    fig3 = px.imshow(heat, text_auto=".1f", color_continuous_scale="RdYlGn",
                     labels=dict(color="ROAS (%)"), aspect="auto")
    st.plotly_chart(fig3, use_container_width=True)

    # 채널별 ROAS + 비용 비중
    ch_agg = filt.groupby("channel").agg(
        cost=("cost","sum"), revenue=("revenue","sum"),
        click=("click","sum"), impression=("impression","sum"),
        purchase=("purchase","sum"), reg=("reg","sum")
    ).reset_index()
    ch_agg["roas_pct"] = ch_agg["revenue"] / ch_agg["cost"].replace(0,np.nan) * 100
    ch_agg["cpa"]      = ch_agg["cost"]    / ch_agg["purchase"].replace(0,np.nan)
    ch_agg["ctr"]      = ch_agg["click"]   / ch_agg["impression"].replace(0,np.nan)

    col_l2, col_r2 = st.columns(2)
    with col_l2:
        st.subheader("채널별 ROAS (%)")
        fig4 = px.bar(ch_agg.sort_values("roas_pct", ascending=False),
                      x="channel", y="roas_pct", color="channel",
                      labels={"roas_pct":"ROAS (%)"})
        fig4.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
        fig4.update_layout(yaxis_ticksuffix="%")
        st.plotly_chart(fig4, use_container_width=True)
    with col_r2:
        st.subheader("채널별 비용 비중")
        fig5 = px.pie(ch_agg, names="channel", values="cost", hole=0.4)
        st.plotly_chart(fig5, use_container_width=True)

    # 캠페인별 ROAS 랭킹
    st.subheader("캠페인별 ROAS 랭킹 (%)")
    cmp_agg = filt.groupby(["channel","campaign"]).agg(
        cost=("cost","sum"), revenue=("revenue","sum"), purchase=("purchase","sum")
    ).reset_index()
    cmp_agg["roas_pct"] = cmp_agg["revenue"] / cmp_agg["cost"].replace(0,np.nan) * 100
    fig6 = px.bar(cmp_agg.sort_values("roas_pct", ascending=False),
                  x="campaign", y="roas_pct", color="channel",
                  labels={"roas_pct":"ROAS (%)","campaign":"캠페인"})
    fig6.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
    fig6.update_layout(yaxis_ticksuffix="%")
    fig6.update_xaxes(tickangle=30)
    st.plotly_chart(fig6, use_container_width=True)
```

- [ ] **Step 2: 브라우저에서 확인**

성과 Overview 탭에서 KPI 8개 카드, 일별 차트, 히트맵, 채널별/캠페인별 차트 정상 렌더링 확인.

- [ ] **Step 3: 커밋**
```bash
git add dashboard/app.py
git commit -m "feat: Overview tab - unified channel + campaign view"
```

---

### Task 5: 소재 분석 탭 — 메시지 카테고리 뷰 추가

**Files:**
- Modify: `dashboard/app.py` — 소재 탭에 메시지 카테고리 분석 섹션 추가

**Interfaces:**
- Consumes: `filt DataFrame(creative, channel, impression, click, cost, revenue, purchase)`
- Produces: 메시지 카테고리별 ROAS 바차트

소재명 파싱 규칙: `{포맷}_{메시지}_{시즌}_...` → 두 번째 `_` 구분 요소가 메시지 카테고리.

- [ ] **Step 1: `with tab_cr:` 블록에서 소재 포맷/채널 섹션 뒤에 메시지 카테고리 섹션 추가**

```python
    # 메시지 카테고리 추출 (소재명 2번째 _ 구분 요소)
    filt_cr = filt.copy()
    filt_cr["msg_category"] = filt_cr["creative"].str.extract(r"^[A-Z]+_([^_]+)_")

    st.subheader("메시지 카테고리별 ROAS (%)")
    msg_agg = filt_cr.groupby("msg_category").agg(
        cost=("cost","sum"), revenue=("revenue","sum"), purchase=("purchase","sum")
    ).reset_index()
    msg_agg["roas_pct"] = msg_agg["revenue"] / msg_agg["cost"].replace(0, np.nan) * 100
    fig_msg = px.bar(
        msg_agg.sort_values("roas_pct", ascending=False),
        x="msg_category", y="roas_pct", color="msg_category",
        text_auto=".1f", labels={"msg_category":"메시지","roas_pct":"ROAS (%)"}
    )
    fig_msg.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
    fig_msg.update_layout(yaxis_ticksuffix="%")
    st.plotly_chart(fig_msg, use_container_width=True)
```

- [ ] **Step 2: 파싱 결과 확인**

```bash
python -c "
import pandas as pd
from pathlib import Path
df = pd.read_parquet('data/raw/channel/2025-01-01_channel.parquet')
df['msg'] = df['소재'].str.extract(r'^[A-Z]+_([^_]+)_')
print(df[['소재','msg']].drop_duplicates())
"
```
Expected: 플러스멤버십, 적립혜택, 할인쿠폰, 배송혜택, 신상품, 특가 등이 `msg` 컬럼에 파싱됨.

- [ ] **Step 3: 브라우저에서 확인**

소재 분석 탭 하단에 메시지 카테고리별 ROAS 바차트 렌더링 확인.

- [ ] **Step 4: 커밋**
```bash
git add dashboard/app.py
git commit -m "feat: creative tab - message category ROAS chart"
```

---

## 자체 검토

**스펙 커버리지:**
- Daily Check 탭 (예산 게이지, 플래그, 비용 delta) → Task 2, 3 ✅
- 성과 Overview 통합 → Task 4 ✅
- 소재 탭 메시지 카테고리 → Task 5 ✅
- EDA / 원본 탭 유지 → 기존 코드 그대로 (변경 없음) ✅
- 예산 파일 로더 → Task 1 ✅

**타입 일관성:**
- `load_budget()` → `pd.DataFrame | None` — Task 2에서 `None` 체크 후 사용 ✅
- `detect_flags(df)` → `pd.DataFrame` — Task 3에서 `empty` 체크 후 렌더링 ✅
- 모든 ROAS 컬럼명 `roas_pct` 통일 ✅
