# ╔══════════════════════════════════════════════════════════════════════╗
# ║  台股全市場選股器 v6.0 — 全功能整合版                                ║
# ║                                                                      ║
# ║  新增功能：                                                          ║
# ║    ① K 線圖互動預覽（Plotly）                                        ║
# ║    ② 停損停利計算器                                                  ║
# ║    ③ 歷史結果儲存（SQLite）                                          ║
# ║    ④ Discord Webhook 推播                                            ║
# ║    ⑤ 簡易回測模組                                                    ║
# ║    ⑥ 多策略切換                                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import time
import warnings
import sqlite3
import json
import os
from datetime import datetime, timedelta

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

# ════════════════════════════════════════════════════════════════════════
# 【頁面設定】
# ════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title            = "台股選股器 v6.0",
    page_icon             = "🏆",
    layout                = "wide",
    initial_sidebar_state = "expanded",
)

# ════════════════════════════════════════════════════════════════════════
# 【CSS 樣式】
# ════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem; border-radius: 12px; margin-bottom: 1.5rem;
        border: 1px solid #e94560; text-align: center;
    }
    .main-header h1 {
        color: #e94560; font-size: 2.2rem; margin: 0;
        text-shadow: 0 0 20px rgba(233,69,96,0.5);
    }
    .main-header p { color: #a8b2d8; margin: 0.5rem 0 0 0; font-size: 1rem; }

    .stock-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #e94560; border-radius: 10px;
        padding: 1rem 1.5rem; margin: 0.5rem 0;
    }
    .stock-card .ticker { color: #e94560; font-size: 1.3rem; font-weight: bold; }
    .stock-card .name   { color: #a8b2d8; font-size: 0.9rem; }
    .stock-card .score  { color: #ffaa44; font-size: 1.8rem; font-weight: bold; }
    .stock-card .price  { color: #66ff88; font-size: 1.1rem; }

    .tp-sl-card {
        background: #0d1117; border: 1px solid #2d3561;
        border-radius: 8px; padding: 0.8rem 1rem; margin: 0.3rem 0;
    }
    .section-divider { border: none; border-top: 1px solid #2d3561; margin: 1.5rem 0; }

    [data-testid="metric-container"] {
        background: #1a1a2e; border: 1px solid #2d3561;
        border-radius: 8px; padding: 1rem;
    }
    [data-testid="stSidebar"] { background-color: #f0f2f6 !important; }
    [data-testid="stSidebar"] * { color: #1a1a2e !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #0f3460 !important; }
    [data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(90deg, #e94560, #0f3460);
        color: white !important; font-weight: bold;
        border: none; border-radius: 8px;
    }
    [data-testid="stSidebar"] hr { border-color: #c0c8d8 !important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# 【資料庫模組】SQLite 歷史結果儲存
# ════════════════════════════════════════════════════════════════════════
DB_PATH = "scan_history.db"

def init_db():
    """初始化 SQLite 資料庫，建立掃描歷史表。"""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS scan_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date   TEXT NOT NULL,
            scan_time   TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            name        TEXT,
            market      TEXT,
            score       INTEGER,
            grade       TEXT,
            close_price REAL,
            change_pct  REAL,
            vol_ratio   REAL,
            signal_date TEXT,
            params_json TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker      TEXT PRIMARY KEY,
            name        TEXT,
            added_date  TEXT,
            note        TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_scan_results(df: pd.DataFrame, params: dict):
    """將本次掃描結果寫入資料庫。"""
    conn        = sqlite3.connect(DB_PATH)
    scan_date   = datetime.now().strftime("%Y-%m-%d")
    scan_time   = datetime.now().strftime("%H:%M:%S")
    params_json = json.dumps(params, ensure_ascii=False)

    for _, row in df.iterrows():
        conn.execute("""
            INSERT INTO scan_results
            (scan_date, scan_time, ticker, name, market, score, grade,
             close_price, change_pct, vol_ratio, signal_date, params_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            scan_date, scan_time,
            row.get("代號",""), row.get("公司名稱",""), row.get("市場",""),
            row.get("推薦指數", 0), row.get("推薦等級",""),
            row.get("收盤價", 0), row.get("漲幅(%)", 0),
            row.get("量比(倍)", 0), row.get("訊號日期",""),
            params_json
        ))
    conn.commit()
    conn.close()


def load_history(days: int = 30) -> pd.DataFrame:
    """讀取最近 N 天的掃描歷史。"""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn      = sqlite3.connect(DB_PATH)
    since     = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df        = pd.read_sql_query(
        "SELECT * FROM scan_results WHERE scan_date >= ? ORDER BY scan_date DESC, score DESC",
        conn, params=(since,)
    )
    conn.close()
    return df


def get_watchlist() -> pd.DataFrame:
    """讀取追蹤清單。"""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query("SELECT * FROM watchlist ORDER BY added_date DESC", conn)
    conn.close()
    return df


def add_to_watchlist(ticker: str, name: str, note: str = ""):
    """加入追蹤清單。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO watchlist (ticker, name, added_date, note)
        VALUES (?,?,?,?)
    """, (ticker, name, datetime.now().strftime("%Y-%m-%d"), note))
    conn.commit()
    conn.close()


def remove_from_watchlist(ticker: str):
    """從追蹤清單移除。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════════════════
# 【樣式輔助函式】純 CSS 著色，零 matplotlib 依賴
# ════════════════════════════════════════════════════════════════════════

def _score_to_color(score) -> str:
    try:
        v = float(score)
    except (TypeError, ValueError):
        return ""
    t = max(0.0, min(1.0, (v - 60) / 40))
    r = 255
    g = int(255 * (1 - t * 0.85))
    b = int(50  * (1 - t))
    return f"background-color:rgb({r},{g},{b});color:#1a1a2e;font-weight:bold;"


def _volratio_to_color(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    t = max(0.0, min(1.0, (v - 2.5) / 5.5))
    r = 255
    g = int(220 * (1 - t))
    b = int(220 * (1 - t))
    return f"background-color:rgb({r},{g},{b});color:#1a1a2e;"


def _chg_to_color(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v >= 0:
        t = min(1.0, v / 10)
        g = int(180 + 75 * t)
        return f"background-color:rgb(50,{g},50);color:#ffffff;"
    else:
        t = min(1.0, abs(v) / 5)
        r = int(180 + 75 * t)
        return f"background-color:rgb({r},50,50);color:#ffffff;"


def _tangle_to_color(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    t = max(0.0, min(1.0, v / 0.05))
    r = int(80  + 175 * t)
    g = int(40  + 215 * t)
    b = int(160 + 95  * t)
    fg = "#fff" if t < 0.5 else "#1a1a2e"
    return f"background-color:rgb({r},{g},{b});color:{fg};"


def _apply_map(styled, func, subset):
    """相容 Pandas 新舊版本的 applymap/map。"""
    pd_ver = tuple(int(x) for x in pd.__version__.split(".")[:2])
    if pd_ver >= (2, 1):
        return styled.map(func, subset=subset)
    return styled.applymap(func, subset=subset)


def style_result_df(df: pd.DataFrame):
    """套用純 CSS 樣式，零 matplotlib 依賴。"""

    def highlight_grade(val):
        s = str(val)
        if "S級" in s: return "background-color:#7b2d00;color:#ff9944;font-weight:bold"
        if "A級" in s: return "background-color:#1a3a1a;color:#66ff66;font-weight:bold"
        if "B級" in s: return "background-color:#1a1a3a;color:#8888ff"
        return ""

    def highlight_gap(val):
        if "🚀" in str(val): return "background-color:#2d1a4a;color:#cc88ff;font-weight:bold"
        return "color:#888888"

    fmt = {
        "推薦指數"      : "{} 分",
        "收盤價"        : "{:.2f}",
        "漲幅(%)"       : "{:+.2f}%",
        "量比(倍)"      : "{:.2f}x",
        "月線斜率(%)"   : "{:+.3f}%",
        "距月線乖離(%)" : "{:.2f}%",
        "實體比例"      : "{:.1%}",
        "均線糾結度"    : lambda x: f"{x:.2%}" if pd.notna(x) else "N/A",
        "跳空缺口(%)"   : "{:+.2f}%",
        "風報比"        : lambda x: f"{x:.2f}" if pd.notna(x) else "N/A",
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styled = df.style

    col_funcs = {
        "推薦指數"  : _score_to_color,
        "量比(倍)"  : _volratio_to_color,
        "漲幅(%)"   : _chg_to_color,
        "均線糾結度": _tangle_to_color,
    }
    for col, fn in col_funcs.items():
        if col in df.columns:
            styled = styled.apply(lambda c, f=fn: [f(v) for v in c], subset=[col])

    if "推薦等級"   in df.columns: styled = _apply_map(styled, highlight_grade, ["推薦等級"])
    if "有跳空缺口" in df.columns: styled = _apply_map(styled, highlight_gap,   ["有跳空缺口"])

    return styled.format(fmt, na_rep="N/A")


def style_score_df(df: pd.DataFrame):
    """加分明細樣式。"""

    def score_color(val, vmin, vmax, r, g, b):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return ""
        t  = max(0.0, min(1.0, (v - vmin) / max(vmax - vmin, 1)))
        ri = int(min(255, r * t + 40))
        gi = int(min(255, g * t + 40))
        bi = int(min(255, b * t + 40))
        fg = "#fff" if t > 0.4 else "#1a1a2e"
        return f"background-color:rgb({ri},{gi},{bi});color:{fg};"

    fmt = {
        "推薦指數"    : "{} 分", "基礎分"      : "{} 分",
        "爆發力加分"  : "+{} 分","籌碼集中加分": "+{} 分",
        "鎖碼強勢加分": "+{} 分","跳空加分"    : "+{} 分",
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styled = df.style
    cfg    = {
        "推薦指數"    : (60,100,255,160,  0),
        "爆發力加分"  : ( 0, 15,220, 50, 50),
        "籌碼集中加分": ( 0, 10,120, 50,200),
        "鎖碼強勢加分": ( 0, 10, 50,100,220),
        "跳空加分"    : ( 0,  5, 50,180, 80),
    }
    for col, (vmin, vmax, r, g, b) in cfg.items():
        if col in df.columns:
            styled = styled.apply(
                lambda c, vmin=vmin, vmax=vmax, r=r, g=g, b=b:
                    [score_color(v, vmin, vmax, r, g, b) for v in c],
                subset=[col]
            )
    return styled.format(fmt, na_rep="N/A")


# ════════════════════════════════════════════════════════════════════════
# 【K 線圖模組】Plotly 互動式 K 線
# ════════════════════════════════════════════════════════════════════════

def plot_candlestick(ticker_yf: str, ticker_name: str, signal_date: str = None):
    """
    繪製互動式 K 線圖（含 MA5/10/20 + 成交量）。
    signal_date：訊號日期，會在圖上標記紅色箭頭。
    """
    if not PLOTLY_OK:
        st.warning("請在 requirements.txt 加入 plotly 套件。")
        return

    try:
        df = yf.download(
            ticker_yf,
            period      = "3mo",
            auto_adjust = True,
            progress    = False,
        )
        if df.empty:
            st.warning(f"無法取得 {ticker_yf} 的資料。")
            return

        # 攤平 MultiIndex（yfinance 新版）
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()
        df["MA5"]  = df["Close"].rolling(5).mean()
        df["MA10"] = df["Close"].rolling(10).mean()
        df["MA20"] = df["Close"].rolling(20).mean()

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
        )

        # K 線
        fig.add_trace(go.Candlestick(
            x     = df.index,
            open  = df["Open"],
            high  = df["High"],
            low   = df["Low"],
            close = df["Close"],
            name  = "K線",
            increasing_line_color  = "#e94560",
            decreasing_line_color  = "#00b894",
            increasing_fillcolor   = "#e94560",
            decreasing_fillcolor   = "#00b894",
        ), row=1, col=1)

        # 均線
        for ma, color in [("MA5","#ffaa44"), ("MA10","#74b9ff"), ("MA20","#a29bfe")]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[ma],
                name=ma, line=dict(color=color, width=1.5),
                hovertemplate=f"{ma}: %{{y:.2f}}<extra></extra>"
            ), row=1, col=1)

        # 訊號日標記
        if signal_date:
            try:
                sig_dt = pd.to_datetime(signal_date)
                if sig_dt in df.index:
                    sig_row = df.loc[sig_dt]
                    fig.add_trace(go.Scatter(
                        x    = [sig_dt],
                        y    = [sig_row["Low"] * 0.97],
                        mode = "markers+text",
                        marker= dict(symbol="triangle-up", size=16, color="#e94560"),
                        text = ["訊號"],
                        textposition="bottom center",
                        textfont=dict(color="#e94560", size=11),
                        name = "訊號日",
                        showlegend=True,
                    ), row=1, col=1)
            except Exception:
                pass

        # 成交量
        colors = [
            "#e94560" if c >= o else "#00b894"
            for c, o in zip(df["Close"], df["Open"])
        ]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"],
            name="成交量", marker_color=colors,
            hovertemplate="成交量: %{y:,.0f}<extra></extra>"
        ), row=2, col=1)

        fig.update_layout(
            title       = f"📈 {ticker_yf.replace('.TW','').replace('.TWO','')} {ticker_name}  近 3 個月 K 線",
            title_font  = dict(color="#e94560", size=16),
            paper_bgcolor = "#0d1117",
            plot_bgcolor  = "#0d1117",
            font          = dict(color="#a8b2d8"),
            xaxis_rangeslider_visible = False,
            legend = dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1,
                bgcolor="rgba(0,0,0,0)",
            ),
            height = 520,
            margin = dict(l=10, r=10, t=60, b=10),
        )
        fig.update_xaxes(
            gridcolor="#1e2a3a", showgrid=True,
            rangebreaks=[dict(bounds=["sat","mon"])]
        )
        fig.update_yaxes(gridcolor="#1e2a3a", showgrid=True)

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"K 線圖繪製失敗：{e}")


# ════════════════════════════════════════════════════════════════════════
# 【停損停利計算器】
# ════════════════════════════════════════════════════════════════════════

def calculate_tp_sl(row: dict) -> dict:
    """
    計算建議停損停利價位與風報比。

    停損邏輯：
      - 第一停損：MA10（跌破短均出場）
      - 第二停損：MA20（趨勢破壞出場）

    停利邏輯：
      - 第一目標：進場價 × 1.08（+8%）
      - 第二目標：進場價 × 1.15（+15%）
      - 第三目標：前高 × 1.05（突破前高後再漲 5%）
    """
    c     = row.get("收盤價", 0)
    ma10  = row.get("MA10",  c * 0.97)
    ma20  = row.get("MA20",  c * 0.94)

    entry      = round(c * 1.005, 2)          # 建議進場：收盤 +0.5%（隔日追）
    sl1        = round(ma10, 2)                # 停損一：MA10
    sl2        = round(ma20, 2)                # 停損二：MA20
    tp1        = round(entry * 1.08, 2)        # 停利一：+8%
    tp2        = round(entry * 1.15, 2)        # 停利二：+15%

    risk       = entry - sl1
    reward1    = tp1 - entry
    rr_ratio   = round(reward1 / risk, 2) if risk > 0 else None

    return {
        "建議進場價" : entry,
        "停損一(MA10)": sl1,
        "停損二(MA20)": sl2,
        "停利一(+8%)" : tp1,
        "停利二(+15%)": tp2,
        "風報比"      : rr_ratio,
    }


# ════════════════════════════════════════════════════════════════════════
# 【Discord 推播模組】
# ════════════════════════════════════════════════════════════════════════

def send_discord(webhook_url: str, df_s: pd.DataFrame, scan_time: str):
    """
    將 S 級標的推送到 Discord Webhook。
    使用 Embed 格式，手機顯示友善。
    """
    if not webhook_url or df_s.empty:
        return False, "無 Webhook URL 或無 S 級標的"

    embeds = []

    # 摘要 embed
    embeds.append({
        "title"      : f"🏆 台股選股器 v6.0 掃描結果",
        "description": f"📅 {scan_time}\n🔥 S 級強烈推薦：**{len(df_s)} 檔**",
        "color"      : 0xe94560,
    })

    # 每檔 S 級標的一個 embed（最多 10 個，Discord 限制）
    for _, row in df_s.head(10).iterrows():
        chg    = row.get("漲幅(%)", 0)
        chg_str= f"{'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%"
        tp_sl  = calculate_tp_sl(row.to_dict())

        embeds.append({
            "title" : f"🔥 {row['代號']} {row.get('公司名稱','')}",
            "color" : 0xff6b35,
            "fields": [
                {"name": "推薦指數", "value": f"**{row['推薦指數']} 分**", "inline": True},
                {"name": "收盤價",   "value": f"**{row['收盤價']:.2f} 元**", "inline": True},
                {"name": "漲幅",     "value": chg_str, "inline": True},
                {"name": "量比",     "value": f"{row['量比(倍)']:.2f}x", "inline": True},
                {"name": "市場",     "value": row.get("市場",""), "inline": True},
                {"name": "訊號日期", "value": row.get("訊號日期",""), "inline": True},
                {"name": "建議進場", "value": f"{tp_sl['建議進場價']:.2f}", "inline": True},
                {"name": "停損(MA10)","value": f"{tp_sl['停損一(MA10)']:.2f}", "inline": True},
                {"name": "風報比",   "value": f"{tp_sl['風報比']}", "inline": True},
            ],
        })

    payload = {"embeds": embeds}

    try:
        res = requests.post(
            webhook_url,
            json    = payload,
            timeout = 10,
            verify  = False,
        )
        if res.status_code in (200, 204):
            return True, "✅ 推播成功！"
        else:
            return False, f"推播失敗：HTTP {res.status_code}"
    except Exception as e:
        return False, f"推播失敗：{e}"


# ════════════════════════════════════════════════════════════════════════
# 【回測模組】
# ════════════════════════════════════════════════════════════════════════

def run_backtest(
        ticker_yf  : str,
        ticker_name: str,
        params     : dict,
        cfg        : dict,
        hold_days  : int = 10,
) -> dict | None:
    """
    對單一股票執行歷史回測。

    邏輯：
      掃描過去 1 年每個交易日，若當日觸發選股條件，
      記錄「進場價（次日開盤）」與「N 日後收盤價」，
      計算報酬率。

    回傳：
      {
        "signals"    : 觸發次數,
        "win_rate"   : 勝率,
        "avg_return" : 平均報酬率,
        "max_return" : 最大單次報酬,
        "min_return" : 最小單次報酬,
        "trades"     : DataFrame（每筆交易明細）,
      }
    """
    try:
        df = yf.download(
            ticker_yf,
            period      = "2y",
            auto_adjust = True,
            progress    = False,
        )
        if df.empty or len(df) < 60:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()
    except Exception:
        return None

    p = params

    # 計算指標
    df["avg_vol_5"] = df["Volume"].shift(1).rolling(p["vol_window"]).mean()
    df["high_20"]   = df["High"].shift(1).rolling(p["high_window"]).max()
    df["ma5"]       = df["Close"].rolling(p["ma_fast"]).mean()
    df["ma10"]      = df["Close"].rolling(p["ma_slow"]).mean()
    df["ma20"]      = df["Close"].rolling(p["ma_month"]).mean()
    cr              = df["High"] - df["Low"]
    df["body_pct"]  = (df["Close"] - df["Low"]) / cr.replace(0, float("nan"))

    trades = []

    # 只回測最近 1 年（避免資料太舊）
    one_year_ago = datetime.now() - timedelta(days=365)
    df_bt = df[df.index >= one_year_ago].copy()

    for i in range(1, len(df_bt) - hold_days):
        row  = df_bt.iloc[i]
        prev = df_bt.iloc[i - 1]

        c   = row["Close"]; o = row["Open"]
        v   = row["Volume"]
        avg = row["avg_vol_5"]
        h20 = row["high_20"]
        ma5 = row["ma5"]; ma10 = row["ma10"]; ma20 = row["ma20"]
        bp  = row["body_pct"]
        pma20 = prev["ma20"]

        # 七大條件
        conds = [
            c >= p["min_price"],
            (avg > p["liquidity_vol"])       if pd.notna(avg) else False,
            (v > avg * p["vol_multiplier"])  if pd.notna(avg) else False,
            (c >= h20)                       if pd.notna(h20) else False,
            (c > o) and pd.notna(bp) and (bp >= p["body_ratio"]),
            pd.notna(ma5) and pd.notna(ma10) and (c > ma5 > ma10),
            pd.notna(ma20) and pd.notna(pma20) and (c > ma20) and (ma20 >= pma20),
        ]
        if not all(conds):
            continue

        # 進場：次日開盤價
        entry_price = df_bt.iloc[i + 1]["Open"]
        # 出場：N 日後收盤價
        exit_price  = df_bt.iloc[i + hold_days]["Close"]
        ret_pct     = (exit_price - entry_price) / entry_price * 100

        trades.append({
            "訊號日期" : df_bt.index[i].strftime("%Y-%m-%d"),
            "進場價"   : round(entry_price, 2),
            "出場價"   : round(exit_price,  2),
            "報酬率(%)": round(ret_pct,     2),
            "結果"     : "✅ 獲利" if ret_pct > 0 else "❌ 虧損",
        })

    if not trades:
        return None

    df_trades = pd.DataFrame(trades)
    rets      = df_trades["報酬率(%)"]

    return {
        "代號"      : ticker_yf.replace(".TW","").replace(".TWO",""),
        "名稱"      : ticker_name,
        "訊號次數"  : len(trades),
        "勝率(%)"   : round(len(rets[rets > 0]) / len(rets) * 100, 1),
        "平均報酬(%)": round(rets.mean(), 2),
        "最大獲利(%)": round(rets.max(),  2),
        "最大虧損(%)": round(rets.min(),  2),
        "trades"    : df_trades,
    }


# ════════════════════════════════════════════════════════════════════════
# 【多策略模組】
# ════════════════════════════════════════════════════════════════════════

def apply_strategy(
        strategy: str,
        ticker  : str,
        df      : pd.DataFrame,
        params  : dict,
        cfg     : dict,
) -> dict | None:
    """
    依選擇的策略套用不同過濾邏輯。
    目前支援：
      - 爆量突破（原 v5.0）
      - 低檔翻揚
      - 均線糾結爆發
    """
    if strategy == "🔥 爆量突破（原版）":
        return apply_filter_v5(ticker, df, params, cfg)
    elif strategy == "📉 低檔翻揚":
        return apply_filter_reversal(ticker, df, params, cfg)
    elif strategy == "🌙 均線糾結爆發":
        return apply_filter_tangle(ticker, df, params, cfg)
    return None


def apply_filter_v5(ticker, df, params, cfg):
    """原版 v5.0 爆量突破策略。"""
    p = params
    required = ["Open","High","Low","Close","Volume"]
    if not all(c in df.columns for c in required):
        return None

    df = df[required].copy().dropna(subset=["Close","Volume"])
    before = len(df)
    df = df[df["Volume"] > 0]
    if before > 0 and (before - len(df)) / before > 0.20:
        return None
    if len(df) < p["min_bars"]:
        return None

    last_date = df.index[-1]
    if hasattr(last_date, "tzinfo") and last_date.tzinfo is not None:
        last_date = last_date.tz_localize(None)
    if (datetime.now() - last_date).days > p["max_days_stale"]:
        return None

    df["avg_vol_5"] = df["Volume"].shift(1).rolling(p["vol_window"]).mean()
    df["high_20"]   = df["High"].shift(1).rolling(p["high_window"]).max()
    df["ma5"]       = df["Close"].rolling(p["ma_fast"]).mean()
    df["ma10"]      = df["Close"].rolling(p["ma_slow"]).mean()
    df["ma20"]      = df["Close"].rolling(p["ma_month"]).mean()
    cr              = df["High"] - df["Low"]
    df["body_pct"]  = (df["Close"] - df["Low"]) / cr.replace(0, float("nan"))
    ma5p  = df["ma5"].shift(1)
    ma10p = df["ma10"].shift(1)
    ma20p = df["ma20"].shift(1)
    stk   = pd.concat([ma5p, ma10p, ma20p], axis=1)
    df["ma_tangle"] = (
        (stk.max(axis=1) - stk.min(axis=1))
        / stk.min(axis=1).replace(0, float("nan"))
    )

    if len(df) < 2:
        return None

    last = df.iloc[-1]; prev = df.iloc[-2]
    o=last["Open"]; h=last["High"]; l=last["Low"]; c=last["Close"]; v=last["Volume"]
    avg_vol=last["avg_vol_5"]; high_20=last["high_20"]
    ma5_v=last["ma5"]; ma10_v=last["ma10"]; ma20_v=last["ma20"]; ma20_pv=prev["ma20"]
    bpct=last["body_pct"]; tangle_v=last["ma_tangle"]
    prev_high=prev["High"]; prev_close=prev["Close"]

    conds = [
        c >= p["min_price"],
        (avg_vol > p["liquidity_vol"])       if pd.notna(avg_vol) else False,
        (v > avg_vol * p["vol_multiplier"])  if pd.notna(avg_vol) else False,
        (c >= high_20)                       if pd.notna(high_20) else False,
        (c > o) and pd.notna(bpct) and (bpct >= p["body_ratio"]),
        pd.notna(ma5_v) and pd.notna(ma10_v) and (c > ma5_v > ma10_v),
        pd.notna(ma20_v) and pd.notna(ma20_pv)
            and (c > ma20_v) and (ma20_v >= ma20_pv),
    ]
    if not all(conds):
        return None

    vol_ratio = v / avg_vol if avg_vol > 0 else 0
    is_gap_up = (l > prev_high) if pd.notna(prev_high) else False
    total_score, breakdown = calculate_recommendation_score(
        vol_ratio, tangle_v, bpct, is_gap_up, cfg
    )
    grade = get_grade_label(total_score, cfg)

    chg_pct    = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0
    ma20_slope = (ma20_v - ma20_pv) / ma20_pv * 100  if ma20_pv > 0   else 0
    ma20_gap   = (c - ma20_v) / ma20_v * 100          if ma20_v > 0    else 0
    gap_size   = (o - prev_close) / prev_close * 100  if prev_close > 0 else 0

    tp_sl = calculate_tp_sl({
        "收盤價": c, "MA10": ma10_v, "MA20": ma20_v
    })

    return {
        "代號"          : ticker.replace(".TW","").replace(".TWO",""),
        "YF代號"        : ticker,
        "策略"          : "🔥 爆量突破",
        "推薦指數"      : total_score,
        "推薦等級"      : grade,
        "基礎分"        : breakdown["基礎分"],
        "爆發力加分"    : breakdown["爆發力"],
        "籌碼集中加分"  : breakdown["籌碼集中"],
        "鎖碼強勢加分"  : breakdown["鎖碼強勢"],
        "跳空加分"      : breakdown["跳空表態"],
        "收盤價"        : round(c,          2),
        "漲幅(%)"       : round(chg_pct,    2),
        "量比(倍)"      : round(vol_ratio,   2),
        "當日量(張)"    : int(v / 1000),
        "5日均量(張)"   : int(avg_vol / 1000),
        "MA5"           : round(ma5_v,      2),
        "MA10"          : round(ma10_v,     2),
        "MA20"          : round(ma20_v,     2),
        "月線斜率(%)"   : round(ma20_slope, 3),
        "距月線乖離(%)" : round(ma20_gap,   2),
        "實體比例"      : round(bpct,       3),
        "均線糾結度"    : round(tangle_v,   4) if pd.notna(tangle_v) else None,
        "跳空缺口(%)"   : round(gap_size,   2),
        "有跳空缺口"    : "🚀 是" if is_gap_up else "— 否",
        "建議進場價"    : tp_sl["建議進場價"],
        "停損一(MA10)"  : tp_sl["停損一(MA10)"],
        "停損二(MA20)"  : tp_sl["停損二(MA20)"],
        "停利一(+8%)"   : tp_sl["停利一(+8%)"],
        "停利二(+15%)"  : tp_sl["停利二(+15%)"],
        "風報比"        : tp_sl["風報比"],
        "訊號日期"      : df.index[-1].strftime("%Y-%m-%d"),
    }


def apply_filter_reversal(ticker, df, params, cfg):
    """
    低檔翻揚策略：
      - 股價在 60 日低點附近（距低點 < 15%）
      - 今日量能放大（> 均量 2 倍）
      - 今日收紅（收盤 > 開盤）
      - MA5 由下往上穿越 MA20
    """
    p = params
    required = ["Open","High","Low","Close","Volume"]
    if not all(c in df.columns for c in required):
        return None

    df = df[required].copy().dropna(subset=["Close","Volume"])
    df = df[df["Volume"] > 0]
    if len(df) < 40:
        return None

    last_date = df.index[-1]
    if hasattr(last_date, "tzinfo") and last_date.tzinfo is not None:
        last_date = last_date.tz_localize(None)
    if (datetime.now() - last_date).days > p["max_days_stale"]:
        return None

    df["avg_vol_5"] = df["Volume"].shift(1).rolling(5).mean()
    df["low_60"]    = df["Low"].rolling(60).min()
    df["ma5"]       = df["Close"].rolling(5).mean()
    df["ma20"]      = df["Close"].rolling(20).mean()
    df["ma5_prev"]  = df["ma5"].shift(1)
    df["ma20_prev"] = df["ma20"].shift(1)

    if len(df) < 2:
        return None

    last = df.iloc[-1]; prev = df.iloc[-2]
    c=last["Close"]; o=last["Open"]; v=last["Volume"]
    avg=last["avg_vol_5"]; low60=last["low_60"]
    ma5=last["ma5"]; ma20=last["ma20"]
    ma5p=last["ma5_prev"]; ma20p=last["ma20_prev"]
    prev_close=prev["Close"]

    conds = [
        c >= p["min_price"],
        pd.notna(avg) and avg > p["liquidity_vol"],
        pd.notna(avg) and v > avg * 2.0,          # 量能放大
        c > o,                                     # 收紅
        pd.notna(low60) and (c - low60) / low60 < 0.15,  # 距低點 < 15%
        pd.notna(ma5) and pd.notna(ma20),
        ma5 > ma20 and ma5p <= ma20p,              # MA5 黃金交叉 MA20
    ]
    if not all(conds):
        return None

    vol_ratio  = v / avg if avg > 0 else 0
    chg_pct    = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0
    tp_sl      = calculate_tp_sl({"收盤價": c, "MA10": ma5, "MA20": ma20})

    return {
        "代號"         : ticker.replace(".TW","").replace(".TWO",""),
        "YF代號"       : ticker,
        "策略"         : "📉 低檔翻揚",
        "推薦指數"     : 70,
        "推薦等級"     : "⭐ A級｜推薦",
        "收盤價"       : round(c,        2),
        "漲幅(%)"      : round(chg_pct,  2),
        "量比(倍)"     : round(vol_ratio, 2),
        "MA5"          : round(ma5,      2),
        "MA20"         : round(ma20,     2),
        "建議進場價"   : tp_sl["建議進場價"],
        "停損一(MA10)" : tp_sl["停損一(MA10)"],
        "停損二(MA20)" : tp_sl["停損二(MA20)"],
        "停利一(+8%)"  : tp_sl["停利一(+8%)"],
        "停利二(+15%)" : tp_sl["停利二(+15%)"],
        "風報比"       : tp_sl["風報比"],
        "訊號日期"     : df.index[-1].strftime("%Y-%m-%d"),
    }


def apply_filter_tangle(ticker, df, params, cfg):
    """
    均線糾結爆發策略：
      - MA5 / MA10 / MA20 三線差距 < 2%（高度糾結）
      - 今日量能爆發（> 均量 3 倍）
      - 今日收紅且突破三線
    """
    p = params
    required = ["Open","High","Low","Close","Volume"]
    if not all(c in df.columns for c in required):
        return None

    df = df[required].copy().dropna(subset=["Close","Volume"])
    df = df[df["Volume"] > 0]
    if len(df) < 35:
        return None

    last_date = df.index[-1]
    if hasattr(last_date, "tzinfo") and last_date.tzinfo is not None:
        last_date = last_date.tz_localize(None)
    if (datetime.now() - last_date).days > p["max_days_stale"]:
        return None

    df["avg_vol_5"] = df["Volume"].shift(1).rolling(5).mean()
    df["ma5"]       = df["Close"].rolling(5).mean()
    df["ma10"]      = df["Close"].rolling(10).mean()
    df["ma20"]      = df["Close"].rolling(20).mean()

    ma5p  = df["ma5"].shift(1)
    ma10p = df["ma10"].shift(1)
    ma20p = df["ma20"].shift(1)
    stk   = pd.concat([ma5p, ma10p, ma20p], axis=1)
    df["tangle_prev"] = (
        (stk.max(axis=1) - stk.min(axis=1))
        / stk.min(axis=1).replace(0, float("nan"))
    )

    if len(df) < 2:
        return None

    last = df.iloc[-1]; prev = df.iloc[-2]
    c=last["Close"]; o=last["Open"]; v=last["Volume"]
    avg=last["avg_vol_5"]
    ma5=last["ma5"]; ma10=last["ma10"]; ma20=last["ma20"]
    tangle=last["tangle_prev"]
    prev_close=prev["Close"]

    ma_max = max(filter(pd.notna, [ma5, ma10, ma20]))

    conds = [
        c >= p["min_price"],
        pd.notna(avg) and avg > p["liquidity_vol"],
        pd.notna(avg) and v > avg * 3.0,           # 強力爆量
        c > o,                                      # 收紅
        pd.notna(tangle) and tangle < 0.02,         # 三線高度糾結
        c > ma_max,                                  # 突破三線
    ]
    if not all(conds):
        return None

    vol_ratio = v / avg if avg > 0 else 0
    chg_pct   = (c - prev_close) / prev_close * 100 if prev_close > 0 else 0
    tp_sl     = calculate_tp_sl({"收盤價": c, "MA10": ma10, "MA20": ma20})

    return {
        "代號"         : ticker.replace(".TW","").replace(".TWO",""),
        "YF代號"       : ticker,
        "策略"         : "🌙 均線糾結爆發",
        "推薦指數"     : 80,
        "推薦等級"     : "⭐ A級｜推薦",
        "收盤價"       : round(c,        2),
        "漲幅(%)"      : round(chg_pct,  2),
        "量比(倍)"     : round(vol_ratio, 2),
        "均線糾結度"   : round(tangle,   4),
        "MA5"          : round(ma5,      2),
        "MA10"         : round(ma10,     2),
        "MA20"         : round(ma20,     2),
        "建議進場價"   : tp_sl["建議進場價"],
        "停損一(MA10)" : tp_sl["停損一(MA10)"],
        "停損二(MA20)" : tp_sl["停損二(MA20)"],
        "停利一(+8%)"  : tp_sl["停利一(+8%)"],
        "停利二(+15%)" : tp_sl["停利二(+15%)"],
        "風報比"       : tp_sl["風報比"],
        "訊號日期"     : df.index[-1].strftime("%Y-%m-%d"),
    }


# ════════════════════════════════════════════════════════════════════════
# 【評分計算】（繼承 v5.0）
# ════════════════════════════════════════════════════════════════════════

def calculate_recommendation_score(vol_ratio, tangle_val, body_pct, is_gap_up, cfg):
    bd = {}
    bd["基礎分"] = cfg["base_score"]
    if vol_ratio >= cfg["vol_tier_high_min"]:
        bd["爆發力"] = cfg["vol_tier_high_score"]
    elif vol_ratio >= cfg["vol_tier_mid_min"]:
        bd["爆發力"] = cfg["vol_tier_mid_score"]
    else:
        bd["爆發力"] = cfg["vol_tier_low_score"]

    if pd.notna(tangle_val):
        if tangle_val < cfg["tangle_tier_high_max"]:
            bd["籌碼集中"] = cfg["tangle_tier_high_score"]
        elif tangle_val < cfg["tangle_tier_mid_max"]:
            bd["籌碼集中"] = cfg["tangle_tier_mid_score"]
        else:
            bd["籌碼集中"] = 0
    else:
        bd["籌碼集中"] = 0

    if pd.notna(body_pct):
        if body_pct >= cfg["body_tier_high_min"]:
            bd["鎖碼強勢"] = cfg["body_tier_high_score"]
        elif body_pct >= cfg["body_tier_mid_min"]:
            bd["鎖碼強勢"] = cfg["body_tier_mid_score"]
        else:
            bd["鎖碼強勢"] = 0
    else:
        bd["鎖碼強勢"] = 0

    bd["跳空表態"] = cfg["gap_up_score"] if is_gap_up else 0
    return min(sum(bd.values()), 100), bd


def get_grade_label(score, cfg):
    if score >= cfg["grade_s_min"]:   return "🔥 S級｜強烈推薦"
    elif score >= cfg["grade_a_min"]: return "⭐ A級｜推薦"
    else:                             return "👀 B級｜觀察"


# ════════════════════════════════════════════════════════════════════════
# 【股票清單抓取】
# ════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_all_stocks() -> pd.DataFrame:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

    df_twse = pd.DataFrame()
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        res.raise_for_status()
        df  = pd.DataFrame(res.json())[["Code","Name"]]
        df.columns = ["代號","名稱"]
        df  = df[df["代號"].str.match(r"^\d{4}$")]
        df["YF代號"] = df["代號"] + ".TW"
        df["市場"]   = "上市(TWSE)"
        df_twse = df
    except Exception as e:
        st.warning(f"⚠️ 上市清單失敗：{e}")

    df_tpex = pd.DataFrame()
    try:
        url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        res.raise_for_status()
        df  = pd.DataFrame(res.json())[["SecuritiesCompanyCode","CompanyName"]]
        df.columns = ["代號","名稱"]
        df  = df[df["代號"].str.match(r"^\d{4}$")]
        df["YF代號"] = df["代號"] + ".TWO"
        df["市場"]   = "上櫃(TPEx)"
        df_tpex = df
    except Exception as e:
        st.warning(f"⚠️ 上櫃清單失敗：{e}")

    frames = [f for f in [df_twse, df_tpex] if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["代號","名稱","YF代號","市場"])
    df_all = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["代號"])
    return df_all.reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════
# 【批次下載】
# ════════════════════════════════════════════════════════════════════════

def download_all_data(stock_list, lookback_days, batch_size, progress_bar, status_text):
    end_str   = datetime.today().strftime("%Y-%m-%d")
    start_str = (datetime.today() - timedelta(days=int(lookback_days*1.5))).strftime("%Y-%m-%d")
    batches   = [stock_list[i:i+batch_size] for i in range(0, len(stock_list), batch_size)]
    all_data  = {}

    for idx, batch in enumerate(batches):
        progress_bar.progress(
            (idx+1)/len(batches),
            text=f"📥 下載中... 第 {idx+1}/{len(batches)} 批（已完成 {len(all_data)} 檔）"
        )
        status_text.markdown(f"⏳ `{batch[0]}` ~ `{batch[-1]}`")
        try:
            raw = yf.download(
                " ".join(batch), start=start_str, end=end_str,
                group_by="ticker", auto_adjust=True, progress=False, threads=True,
            )
            if len(batch) == 1:
                if not raw.empty:
                    all_data[batch[0]] = raw.dropna(how="all")
            else:
                for t in batch:
                    try:
                        d = raw[t].dropna(how="all")
                        if not d.empty and len(d) >= 10:
                            all_data[t] = d
                    except (KeyError, TypeError):
                        pass
        except Exception:
            pass
        if idx < len(batches)-1:
            time.sleep(1.5)

    return all_data


# ════════════════════════════════════════════════════════════════════════
# 【主程式 UI】
# ════════════════════════════════════════════════════════════════════════

def main():
    init_db()

    st.markdown("""
    <div class="main-header">
        <h1>🏆 台股全市場選股器 v6.0</h1>
        <p>全功能版 — 爆量突破 × K線預覽 × 停損停利 × 回測驗證 × Discord 推播</p>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════
    # 【側邊欄】
    # ════════════════════════════════════════════════════════════════
    with st.sidebar:
        st.markdown("## ⚙️ 策略參數調整")
        st.markdown("---")

        # 策略選擇
        st.markdown("### 🎯 選股策略")
        strategy = st.selectbox(
            "選擇策略",
            ["🔥 爆量突破（原版）", "📉 低檔翻揚", "🌙 均線糾結爆發"],
            help="不同策略使用不同的選股邏輯"
        )

        st.markdown("### 📊 掃描範圍")
        market_choice = st.radio(
            "掃描市場",
            ["🏢 上市 + 上櫃（全市場）", "🏢 僅上市（TWSE）", "🏪 僅上櫃（TPEx）"],
        )
        lite_mode     = st.toggle("⚡ 輕量模式（雲端推薦）", value=True)
        lookback_days = st.slider("歷史資料天數",  45,  90,  60,  5)
        batch_size    = st.slider("批次下載大小",  20, 100,  50, 10)

        st.markdown("---")
        st.markdown("### 🛡️ 基礎過濾條件")
        min_price      = st.slider("最低股價（元）",     5,   50,  15,  5)
        liquidity_vol  = st.slider("最低流
