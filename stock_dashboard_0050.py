"""
台股個股視覺化分析儀表板（Streamlit 版）
================================================
執行方式：
    cd streamlit_dashboard
    pip install -r requirements.txt
    streamlit run stock_dashboard.py

資料來源：專案根目錄的 db 資料夾
    price0050.db   0050 成份股行情（price）
    market.db      加權指數（taiex）
    chip0050.db    0050 成份股籌碼（institutional）
    revenue0050.db 0050 成份股月營收（revenue）
    fs_summary0050.db 0050 成份股財報（income_statement、balance_sheet、cashflow、financial_analysis）
    stock.db       公司與分類（company、stock_sub_industry、revenue_mix、stock_theme）

單位換算：金額由「仟元」換算為「億元」（÷ 100,000）；股數換算為「張」（÷ 1,000）。
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# ----------------------------------------------------------------------
# 基本設定
# ----------------------------------------------------------------------

DB_DIR = Path(__file__).resolve().parent / "db"

# 淺色莫蘭迪色系（Morandi Palette）：低彩度但加深明度，確保在淺底上對比清楚
C = {
    "rose": "#A8655D", "sage": "#5E8571", "blue": "#5B7194", "sand": "#A88A4E",
    "mauve": "#84667F", "olive": "#7C8159", "grey": "#CFC8BE",
    "up": "#A8544B", "down": "#4F7F65",  # 台股慣例：紅漲綠跌
    "bg": "#F6F3EE", "panel": "#FFFEFC", "fg": "#33302D", "muted": "#6B655F",
    "line": "#E3DCD2", "side": "#ECE6DD",
}

st.set_page_config(page_title="台股個股分析", page_icon="📈", layout="wide")

# 主題已由 .streamlit/config.toml 設為淺色；以下 CSS 為備援，
# 即使系統 / 瀏覽器為深色模式，也強制文字與元件維持深字淺底。
st.markdown(
    f"""
    <style>
    .stApp, [data-testid="stHeader"] {{ background-color: {C['bg']}; color: {C['fg']}; }}
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li, .stApp label,
    .stApp span, [data-testid="stMarkdownContainer"] {{ color: {C['fg']}; }}
    [data-testid="stSidebar"] {{ background-color: {C['side']}; }}
    [data-testid="stSidebar"] * {{ color: {C['fg']}; }}
    [data-testid="stWidgetLabel"] p {{ color: {C['fg']} !important; font-weight: 600; }}
    [data-testid="stCaptionContainer"], .stApp small {{ color: {C['muted']} !important; }}
    /* 輸入框 */
    .stApp input, [data-baseweb="input"], [data-baseweb="base-input"],
    [data-testid="stNumberInputContainer"], [data-testid="stNumberInput"] button {{
        background-color: {C['panel']} !important; color: {C['fg']} !important;
        border-color: {C['grey']} !important;
    }}
    [data-testid="stNumberInput"] button svg {{ fill: {C['fg']}; }}
    /* 滑桿數值 */
    [data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"],
    [data-testid="stSliderTickBarMax"] {{ color: {C['rose']} !important; font-weight: 600; }}
    /* 指標卡 */
    [data-testid="stMetric"] {{
        background: {C['panel']}; border: 1px solid {C['line']};
        border-radius: 10px; padding: 12px 16px; border-top: 3px solid {C['rose']};
    }}
    [data-testid="stMetricLabel"] p {{ color: {C['muted']} !important; font-weight: 600; }}
    [data-testid="stMetricValue"] {{ color: {C['fg']} !important; }}
    /* 分頁 */
    .stTabs [data-baseweb="tab"] p {{ color: {C['muted']}; font-weight: 600; }}
    .stTabs [aria-selected="true"] p {{ color: {C['rose']} !important; }}
    /* 提示框 */
    [data-testid="stAlert"] {{ background-color: #E6ECF2; }}
    [data-testid="stAlert"] p {{ color: #2F4A66 !important; }}
    .note {{ color: {C['muted']} !important; font-size: 0.88rem; margin-top: -0.6rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------
# 資料讀取（使用 st.cache_data 快取，切換參數時不必重新查詢）
# ----------------------------------------------------------------------
def db_ok(db: str) -> bool:
    """資料庫檔案存在且非空檔。"""
    path = DB_DIR / f"{db}.db"
    return path.is_file() and path.stat().st_size > 0


def query(db: str, sql: str, params: tuple = ()) -> pd.DataFrame:
    """以唯讀模式連線到 db/ 下指定的資料庫並執行 SQL，回傳 DataFrame。
    資料庫或資料表不存在時回傳空 DataFrame（唯讀模式也避免 sqlite 自動建立空檔）。"""
    if not db_ok(db):
        return pd.DataFrame()
    try:
        with sqlite3.connect(f"{(DB_DIR / f'{db}.db').as_uri()}?mode=ro", uri=True) as conn:
            return pd.read_sql(sql, conn, params=params)
    except (sqlite3.Error, pd.errors.DatabaseError):
        return pd.DataFrame()


@st.cache_data
def load_stock_list() -> pd.DataFrame:
    """price 資料表中所有成份股（代碼＋最新名稱），供 sidebar 下拉選單使用。"""
    return query("price0050", """
        SELECT p.sid, p.sname FROM price p
        JOIN (SELECT sid, MAX(date) AS date FROM price GROUP BY sid) m
          ON p.sid = m.sid AND p.date = m.date
        ORDER BY p.sid""")


@st.cache_data
def load_price(sid: str) -> pd.DataFrame:
    df = query("price0050", "SELECT * FROM price WHERE sid = ? ORDER BY date", (sid,))
    if df.empty:
        return df
    taiex = query("market", "SELECT date, close AS taiex FROM taiex WHERE date >= ? ORDER BY date",
                  (df["date"].min(),))
    if taiex.empty:
        df["taiex"] = float("nan")
    else:
        df = df.merge(taiex, on="date", how="left")
    df["date"] = pd.to_datetime(df["date"])
    df["成交量張"] = df["volume"] / 1000
    df["成交值億"] = df["amount"] / 1e8
    return df


@st.cache_data
def load_institutional(sid: str) -> pd.DataFrame:
    df = query("chip0050", """
        SELECT date, 外資買賣超, 投信買賣超, 自營商買賣超, 三大法人買賣超
        FROM institutional WHERE sid = ? ORDER BY date""", (sid,))
    df["date"] = pd.to_datetime(df["date"])
    for col in ["外資買賣超", "投信買賣超", "自營商買賣超", "三大法人買賣超"]:
        df[col] = df[col] / 1000  # 股 → 張
    return df


@st.cache_data
def load_revenue(sid: str) -> pd.DataFrame:
    df = query("revenue0050", """
        SELECT date, 當月營收, MoM, YoY, 累計YoY, 備註
        FROM revenue WHERE sid = ? ORDER BY date""", (sid,))
    df["月份"] = df["date"].str[:7]
    df["營收億"] = df["當月營收"] / 1e5  # 仟元 → 億元
    return df


@st.cache_data
def load_quarterly(sid: str) -> pd.DataFrame:
    """合併單季損益、資產負債、現金流量，並計算三率與比率。"""
    inc = query("fs_summary0050", """
        SELECT year, season, 營業收入, "營業毛利（毛損）" AS 毛利, "營業利益（損失）" AS 營益,
               營業外收入及支出 AS 業外, "本期淨利（淨損）" AS 淨利,
               "淨利（淨損）歸屬於母公司業主" AS 母公司淨利, EPS
        FROM income_statement WHERE sid = ? ORDER BY year, season""", (sid,))
    bs = query("fs_summary0050", """
        SELECT year, season, 資產總計, 負債總計, 流動資產, 流動負債, 每股參考淨值
        FROM balance_sheet WHERE sid = ? ORDER BY year, season""", (sid,))
    cf = query("fs_summary0050", """
        SELECT year, season,
               "營業活動之淨現金流入（流出）" AS 營運CF,
               "投資活動之淨現金流入（流出）" AS 投資CF,
               "籌資活動之淨現金流入（流出）" AS 籌資CF
        FROM cashflow WHERE sid = ? ORDER BY year, season""", (sid,))
    # 現金流量表是年初累計值 → 同年度相減得到單季值
    for col in ["營運CF", "投資CF", "籌資CF"]:
        cf[col] = cf.groupby("year")[col].diff().fillna(cf[col])

    df = inc.merge(bs, on=["year", "season"], how="left").merge(cf, on=["year", "season"], how="left")
    df["季別"] = df["year"].astype(str) + "Q" + df["season"].astype(str)
    df["營收億"] = df["營業收入"] / 1e5
    df["毛利率"] = df["毛利"] / df["營業收入"] * 100
    df["營益率"] = df["營益"] / df["營業收入"] * 100
    df["淨利率"] = df["淨利"] / df["營業收入"] * 100
    df["業外億"] = df["業外"] / 1e5
    df["母公司淨利億"] = df["母公司淨利"] / 1e5
    df["負債比率"] = df["負債總計"] / df["資產總計"] * 100
    df["流動比率"] = df["流動資產"] / df["流動負債"] * 100
    for col in ["營運CF", "投資CF"]:
        df[col + "億"] = df[col] / 1e5
    df["自由現金流億"] = df["營運CF億"] + df["投資CF億"]
    return df


@st.cache_data
def load_annual(sid: str) -> pd.DataFrame:
    return query("fs_summary0050", "SELECT * FROM financial_analysis WHERE sid = ? ORDER BY year", (sid,))


@st.cache_data
def load_profile(sid: str):
    company = query("stock", """
        SELECT c.*, s.產業 AS CMoney產業, s.細產業別, s.經營項目
        FROM company c LEFT JOIN stock_sub_industry s ON c.sid = s.sid
        WHERE c.sid = ?""", (sid,))
    mix = query("stock", "SELECT revenue_mix, crawl_date FROM revenue_mix WHERE sid = ?", (sid,))
    themes = query("stock", "SELECT type, theme_name FROM stock_theme WHERE sid = ? ORDER BY type, theme_name", (sid,))
    return company, mix, themes


# ----------------------------------------------------------------------
# 畫圖小工具
# ----------------------------------------------------------------------
def style(fig: go.Figure, height: int = 360, yfmt: str = None) -> go.Figure:
    """套用一致的淺色莫蘭迪樣式。"""
    fig.update_layout(
        height=height, paper_bgcolor=C["panel"], plot_bgcolor=C["panel"],
        font=dict(color=C["fg"], size=13), hovermode="x unified",
        # 左、下留足空間給座標刻度，並開啟 automargin 讓 Plotly 依標籤長度自動擴張
        margin=dict(l=70, r=20, t=40, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(showgrid=False, linecolor=C["line"], automargin=True,
                     tickfont=dict(color=C["fg"]))
    fig.update_yaxes(gridcolor=C["line"], zerolinecolor="#B9B2A8", tickformat=yfmt,
                     automargin=True, tickfont=dict(color=C["fg"]))
    return fig


def skip_gaps(fig: go.Figure, dates) -> go.Figure:
    """把資料中沒有的日期（週末、國定假日、休市日）從 X 軸剔除，讓走勢連續。"""
    dates = pd.to_datetime(pd.Series(dates)).dt.normalize()
    all_days = pd.date_range(dates.min(), dates.max(), freq="D")
    missing = all_days.difference(dates).strftime("%Y-%m-%d").tolist()
    fig.update_xaxes(rangebreaks=[dict(values=missing)])
    return fig


def line(fig, x, y, name, color, width=2, dash=None, **kw):
    fig.add_trace(go.Scatter(x=x, y=y, name=name, mode="lines",
                             line=dict(color=color, width=width, dash=dash), **kw))


def note(text: str):
    st.markdown(f"<p class='note'>{text}</p>", unsafe_allow_html=True)


def signed(v, fmt=",.0f"):
    return f"{v:+{fmt}}"


# ----------------------------------------------------------------------
# Sidebar：使用者輸入與參數
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("🔎 查詢設定")
    stocks = load_stock_list()
    names = dict(zip(stocks["sid"], stocks["sname"]))
    sid_list = stocks["sid"].tolist()
    sid = st.selectbox(
        "股票代碼（Stock ID）", sid_list,
        index=sid_list.index("2330") if "2330" in sid_list else 0,
        format_func=lambda s: f"{s} {names[s]}",
        help="0050 成份股，可直接輸入代碼或名稱搜尋",
    )

    st.subheader("顯示參數")
    period = st.select_slider(
        "股價觀察期間（Period）",
        options=["1個月", "3個月", "6個月", "1年", "全部"], value="1年",
        help="股價、評價倍數與相對大盤圖的時間範圍",
    )
    ma_short, ma_long = st.slider(
        "移動平均線天數（Moving Average）", min_value=5, max_value=120, value=(20, 60), step=5,
        help="左端為短期均線、右端為長期均線",
    )
    rev_years = st.slider("月營收顯示年數（Revenue Years）", 1, 10, 3,
                          help="月營收長條圖與年增率圖往回顯示的年數")
    n_quarters = st.slider("財報顯示季數（Quarters）", 4, 40, 12, step=4,
                           help="EPS、三率、現金流量等季度圖表往回顯示的季數")
    inst_days = st.number_input("法人買賣超統計天數（Days）", 5, 120, 20, step=5,
                                help="頁首 KPI 中外資、投信近 N 個交易日買賣超合計")

    missing_db = [f"{d}.db" for d in ("market", "stock") if not db_ok(d)]
    if missing_db:
        st.warning(f"db/ 缺少或為空檔：{'、'.join(missing_db)}，相關圖表將不顯示。")

    st.caption("資料來源：課堂資料庫 db/（證交所、櫃買中心、公開資訊觀測站、MoneyDJ、CMoney）。本頁僅供教學使用，不構成投資建議。")


# ----------------------------------------------------------------------
# 讀取資料
# ----------------------------------------------------------------------
if not sid:
    st.info("請在左側選擇股票代碼。")
    st.stop()

price_all = load_price(sid)
if price_all.empty:
    st.error(f"資料庫中找不到股票代碼「{sid}」的行情資料，請確認代碼是否正確。")
    st.stop()

inst = load_institutional(sid)
rev = load_revenue(sid)
qtr = load_quarterly(sid)
annual = load_annual(sid)
company, mix, themes = load_profile(sid)

# 均線要用完整資料計算，再依觀察期間裁切，避免期間開頭出現空值
price_all[f"MA{ma_short}"] = price_all["close"].rolling(ma_short).mean()
price_all[f"MA{ma_long}"] = price_all["close"].rolling(ma_long).mean()

days = {"1個月": 30, "3個月": 91, "6個月": 182, "1年": 365, "全部": None}[period]
if days:
    price = price_all[price_all["date"] >= price_all["date"].max() - pd.Timedelta(days=days)].copy()
else:
    price = price_all.copy()

sname = price_all["sname"].iloc[-1]
en_name = company["英文簡稱"].iloc[0] if not company.empty else ""

# ----------------------------------------------------------------------
# 頁首與 KPI
# ----------------------------------------------------------------------
st.title(f"{sid} {sname}")
st.caption(f"{en_name}｜個股視覺化分析｜最新交易日 {price_all['date'].max():%Y-%m-%d}")

last, prev, first = price_all.iloc[-1], price_all.iloc[-2], price.iloc[0]
chg_period = (last["close"] / first["close"] - 1) * 100
chg_taiex = (last["taiex"] / first["taiex"] - 1) * 100

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("收盤價（Close）", f"{last['close']:,.2f}",
          f"{(last['close'] / prev['close'] - 1) * 100:+.2f}%（日）", delta_color="inverse")
k2.metric("本益比（P/E）", "—" if pd.isna(last["PE"]) else f"{last['PE']:.2f}",
          None if pd.isna(last["PB"]) else f"P/B {last['PB']:.2f}", delta_color="off")
if not rev.empty:
    r = rev.iloc[-1]
    k3.metric(f"月營收（{r['月份']}）", f"{r['營收億']:,.2f} 億", f"YoY {r['YoY']:+.2f}%", delta_color="inverse")
if not qtr.empty:
    q = qtr.iloc[-1]
    q_prev = qtr.iloc[-2]["EPS"] if len(qtr) > 1 else None
    k4.metric(f"單季 EPS（{q['季別']}）", f"{q['EPS']:.2f} 元",
              None if q_prev is None else f"前季 {q_prev:.2f}", delta_color="off")
if not inst.empty:
    recent = inst.tail(int(inst_days))
    k5.metric(f"外資近 {inst_days} 日", f"{recent['外資買賣超'].sum():+,.0f} 張",
              f"投信 {recent['投信買賣超'].sum():+,.0f} 張", delta_color="inverse")
# 註：台股紅漲綠跌，與 Streamlit 預設（綠漲紅跌）相反，因此用 delta_color="inverse"

# 一句話總結（Takeaway）
summary = [f"近{period}股價 {chg_period:+.1f}%"
           + ("" if pd.isna(chg_taiex) else f"，同期加權指數 {chg_taiex:+.1f}%")]
if not rev.empty:
    record = "，為資料期間單月新高" if r["營收億"] >= rev["營收億"].max() else ""
    summary.append(f"{r['月份']} 營收 {r['營收億']:,.1f} 億元、YoY {r['YoY']:+.1f}%{record}")
if not qtr.empty:
    summary.append(f"{q['季別']} EPS {q['EPS']:.2f} 元、毛利率 {q['毛利率']:.1f}%")
st.info("；".join(summary) + "。")

# ----------------------------------------------------------------------
# 分頁
# ----------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["股價與籌碼", "營收動能", "獲利能力", "財務體質", "公司概況"])

# ---------- 分頁 1：股價與籌碼 ----------
with tab1:
    st.subheader("收盤價與移動平均線　Close & Moving Average")
    note(f"MA{ma_short}／MA{ma_long} 為 {ma_short}／{ma_long} 個交易日平均收盤價；下方為成交量（Volume，張），紅色為收漲、綠色為收跌。")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.04)
    fig.add_trace(go.Scatter(x=price["date"], y=price["close"], name="收盤價",
                             line=dict(color=C["rose"], width=2.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=price["date"], y=price[f"MA{ma_short}"], name=f"MA{ma_short}",
                             line=dict(color=C["blue"], width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=price["date"], y=price[f"MA{ma_long}"], name=f"MA{ma_long}",
                             line=dict(color=C["sand"], width=1.6)), row=1, col=1)
    up = price["close"].diff().fillna(0) >= 0
    fig.add_trace(go.Bar(x=price["date"], y=price["成交量張"], name="成交量（張）",
                         marker_color=["#CFA39D" if u else "#9FBBA9" for u in up], showlegend=False),
                  row=2, col=1)
    st.plotly_chart(skip_gaps(style(fig, 460, ",.0f"), price["date"]), width="stretch", theme=None)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("相對大盤表現　vs. TAIEX")
        note("以觀察期間第一個交易日為 100，比較個股與加權指數的累積漲幅。")
        fig = go.Figure()
        line(fig, price["date"], price["close"] / price["close"].iloc[0] * 100, sname, C["rose"])
        if price["taiex"].notna().any():
            line(fig, price["date"], price["taiex"] / price["taiex"].iloc[0] * 100, "加權指數", C["blue"])
        else:
            note("（缺少 market.db，無加權指數資料）")
        st.plotly_chart(skip_gaps(style(fig, yfmt=",.0f"), price["date"]), width="stretch", theme=None)
    with c2:
        st.subheader("本益比與股價淨值比　P/E & P/B")
        note("交易所每日公布的評價倍數；ETF 沒有這兩項數字。")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=price["date"], y=price["PE"], name="P/E（左軸）",
                                 line=dict(color=C["sand"], width=2)), secondary_y=False)
        fig.add_trace(go.Scatter(x=price["date"], y=price["PB"], name="P/B（右軸）",
                                 line=dict(color=C["mauve"], width=2)), secondary_y=True)
        st.plotly_chart(skip_gaps(style(fig), price["date"]), width="stretch", theme=None)

    st.subheader("三大法人累計買賣超　Institutional Investors（張）")
    note("籌碼資料期間逐日累加：外資（Foreign Investors）、投信（Investment Trust）、自營商（Dealers）。")
    if inst.empty:
        st.warning("查無三大法人資料。")
    else:
        fig = go.Figure()
        for col, name, color in [("外資買賣超", "外資", C["blue"]), ("投信買賣超", "投信", C["rose"]),
                                 ("自營商買賣超", "自營商", C["olive"])]:
            line(fig, inst["date"], inst[col].cumsum(), name, color)
        st.plotly_chart(skip_gaps(style(fig, yfmt=",.0f"), inst["date"]), width="stretch", theme=None)

# ---------- 分頁 2：營收動能 ----------
with tab2:
    if rev.empty:
        st.warning("查無月營收資料。")
    else:
        rv = rev.tail(rev_years * 12)
        st.subheader("每月營收　Monthly Revenue（億元）")
        note(f"近 {rev_years} 年逐月營收；深色為最近 12 個月。")
        colors = [C["rose"] if i >= len(rv) - 12 else "#C3CEC6" for i in range(len(rv))]
        fig = go.Figure(go.Bar(x=rv["月份"], y=rv["營收億"], marker_color=colors, name="營收（億）",
                               customdata=rv[["YoY", "MoM"]],
                               hovertemplate="%{x}<br>營收 %{y:,.2f} 億<br>YoY %{customdata[0]:+.2f}%"
                                             "<br>MoM %{customdata[1]:+.2f}%<extra></extra>"))
        st.plotly_chart(style(fig, yfmt=",.0f"), width="stretch", theme=None)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("營收年增率　YoY Growth（%）")
            note("與去年同月相比；累計 YoY 為年初至當月累計營收的年增率。")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=rv["月份"], y=rv["YoY"], name="YoY", mode="lines+markers",
                                     line=dict(color=C["rose"], width=2), marker=dict(size=5)))
            line(fig, rv["月份"], rv["累計YoY"], "累計 YoY", C["blue"], width=1.6)
            fig.add_hline(y=0, line_dash="dash", line_color="#B9B2A8")
            st.plotly_chart(style(fig), width="stretch", theme=None)
        with c2:
            st.subheader("近 12 個月營收明細")
            note("月增率（MoM）、年增率（YoY）、累計年增率（Cumulative YoY）。")
            table = rv.tail(12).iloc[::-1][["月份", "營收億", "MoM", "YoY", "累計YoY", "備註"]]
            st.dataframe(
                table.style.format({"營收億": "{:,.2f}", "MoM": "{:+.2f}", "YoY": "{:+.2f}", "累計YoY": "{:+.2f}"},
                                   na_rep=""),
                hide_index=True, width="stretch", height=460,
            )

# ---------- 分頁 3：獲利能力 ----------
with tab3:
    if qtr.empty:
        st.warning("查無季報資料。")
    else:
        qq = qtr.tail(n_quarters)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("單季每股盈餘　Quarterly EPS（元）")
            note("由累計 EPS 相減得到的單季近似值；最新一季以深色標示。")
            colors = [C["down"] if v < 0 else C["rose"] if i == len(qq) - 1 else C["blue"]
                      for i, v in enumerate(qq["EPS"])]
            fig = go.Figure(go.Bar(x=qq["季別"], y=qq["EPS"], marker_color=colors, name="EPS",
                                   text=qq["EPS"].round(2), textposition="outside"))
            st.plotly_chart(style(fig), width="stretch", theme=None)
        with c2:
            st.subheader("獲利三率　Gross / Operating / Net Margin（%）")
            note("淨利率高於營益率時，代表業外收益貢獻大。")
            fig = go.Figure()
            line(fig, qq["季別"], qq["毛利率"], "毛利率", C["rose"])
            line(fig, qq["季別"], qq["營益率"], "營業利益率", C["blue"])
            line(fig, qq["季別"], qq["淨利率"], "淨利率", C["sage"])
            st.plotly_chart(style(fig, yfmt=".1f"), width="stretch", theme=None)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("本業 vs. 業外　Net Income & Non-operating Income（億元）")
            note("比較母公司淨利與營業外收支（Non-operating Income），觀察獲利是否來自本業。")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=qq["季別"], y=qq["母公司淨利億"], name="母公司淨利", marker_color=C["blue"]))
            fig.add_trace(go.Bar(x=qq["季別"], y=qq["業外億"], name="業外收支", marker_color=C["sand"]))
            st.plotly_chart(style(fig, yfmt=",.0f").update_layout(barmode="group"), width="stretch", theme=None)
        with c2:
            st.subheader("年度報酬率　ROE & ROA（%）")
            note("權益報酬率（Return on Equity）與資產報酬率（Return on Assets）。")
            if annual.empty:
                st.warning("查無年度財務比率。")
            else:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=annual["year"].astype(str), y=annual["ROE"], name="ROE",
                                         mode="lines+markers", line=dict(color=C["rose"], width=2)))
                fig.add_trace(go.Scatter(x=annual["year"].astype(str), y=annual["ROA"], name="ROA",
                                         mode="lines+markers", line=dict(color=C["sage"], width=2)))
                st.plotly_chart(style(fig, yfmt=".1f"), width="stretch", theme=None)

# ---------- 分頁 4：財務體質 ----------
with tab4:
    if qtr.empty:
        st.warning("查無季報資料。")
    else:
        qq = qtr.tail(n_quarters)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("負債比率與流動比率　Debt & Current Ratio（%）")
            note("負債總計 ÷ 資產總計；流動資產 ÷ 流動負債。")
            fig = go.Figure()
            line(fig, qq["季別"], qq["流動比率"], "流動比率", C["blue"])
            line(fig, qq["季別"], qq["負債比率"], "負債比率", C["rose"])
            st.plotly_chart(style(fig, yfmt=".0f"), width="stretch", theme=None)
        with c2:
            st.subheader("單季現金流量　Cash Flow（億元）")
            note("營業現金流（Operating CF）＋投資現金流（Investing CF）＝自由現金流（Free Cash Flow）。")
            fig = go.Figure()
            for col, name, color in [("營運CF億", "營業現金流", C["sage"]), ("投資CF億", "投資現金流", C["rose"]),
                                     ("自由現金流億", "自由現金流", C["blue"])]:
                fig.add_trace(go.Bar(x=qq["季別"], y=qq[col], name=name, marker_color=color))
            st.plotly_chart(style(fig, yfmt=",.0f").update_layout(barmode="group"), width="stretch", theme=None)

    st.subheader("年度財務比率　Financial Ratios")
    note("每年 4 月更新前一年度；週轉率單位為「次」、日數為「日」。")
    if not annual.empty:
        cols = ["year", "EPS", "ROE", "ROA", "純益率", "負債比率", "流動比率", "速動比率",
                "存貨週轉率", "平均收現日數", "固定資產週轉率", "現金流量比率"]
        st.dataframe(annual[cols].iloc[::-1].style.format({c: "{:,.2f}" for c in cols[1:]}, na_rep=""),
                     hide_index=True, width="stretch")

# ---------- 分頁 5：公司概況 ----------
with tab5:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("公司基本資料　Company Profile")
        if company.empty:
            st.warning("查無公司基本資料。")
        else:
            co = company.iloc[0]
            info = {
                "公司名稱": co["公司名稱"],
                "市場別／產業": f"{co['市場別']}／{co['產業別名稱']}",
                "細產業（CMoney）": f"{co['細產業別'] or '—'}｜{co['經營項目'] or '—'}",
                "董事長／總經理": f"{co['董事長']}／{co['總經理']}",
                "成立日期": str(co["成立日期"])[:10],
                "上市（櫃）日期": str(co["上市日期"])[:10],
                "實收資本額": f"{co['實收資本額'] / 1e8:,.2f} 億元",
                "網址": co["網址"],
            }
            st.table(pd.DataFrame(info.items(), columns=["項目", "內容"]).set_index("項目"))
    with c2:
        st.subheader("營收比重　Revenue Mix")
        if mix.empty:
            st.warning("查無營收比重資料。")
        else:
            m = mix.iloc[0]
            note(f"資料年度 {str(m['crawl_date'])[:4]}（依爬取日期 {m['crawl_date']}），出自公司年報（MoneyDJ 整理）。")
            # 將「印刷電路板(PCB)99.07%、其他0.93%」拆成項目與比例
            items = pd.Series(m["revenue_mix"].split("、")).str.extract(r"^(.*?)([\d.]+)%$").dropna()
            items.columns = ["項目", "比重"]
            items["比重"] = items["比重"].astype(float)
            fig = go.Figure(go.Pie(labels=items["項目"], values=items["比重"], hole=0.55, sort=False,
                                   marker=dict(colors=[C["sage"], C["sand"], C["rose"], C["blue"], C["mauve"]])))
            st.plotly_chart(style(fig, 300).update_layout(hovermode=False), width="stretch", theme=None)

        st.subheader(f"所屬集團股與概念股（{len(themes)} 個）")
        if not themes.empty:
            for t, g in themes.groupby("type"):
                st.markdown(f"**{t}**：" + "、".join(g["theme_name"]))
