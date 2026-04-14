# ╔══════════════════════════════════════════════════════════════════════╗
# ║  台股全市場選股器 v6.0 — 全功能整合版                                ║
# ║  新增：K線預覽 / 停損停利 / 歷史儲存 / Discord推播 / 回測 / 多策略  ║
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

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);
        padding:2rem; border-radius:12px; margin-bottom:1.5rem;
        border:1px solid #e94560; text-align:center;
    }
    .main-header h1 { color:#e94560; font-size:2.2rem; margin:0; text-shadow:0 0 20px rgba(233,69,96,0.5); }
    .main-header p  { color:#a8b2d8; margin:0.5rem 0 0 0; font-size:1rem; }
    .stock-card {
        background:linear-gradient(135deg,#1a1a2e,#16213e);
        border:1px solid #e94560; border-radius:10px; padding:1rem 1.5rem; margin:0.5rem 0;
    }
    .stock-card .ticker { color:#e94560; font-size:1.3rem; font-weight:bold; }
    .stock-card .name   { color:#a8b2d8; font-size:0.9rem; }
    .stock-card .score  { color:#ffaa44; font-size:1.8rem; font-weight:bold; }
    .stock-card .price  { color:#66ff88; font-size:1.1rem; }
    .section-divider    { border:none; border-top:1px solid #2d3561; margin:1.5rem 0; }
    [data-testid="metric-container"] {
        background:#1a1a2e; border:1px solid #2d3561; border-radius:8px; padding:1rem;
    }
    [data-testid="stSidebar"]    { background-color:#f0f2f6 !important; }
    [data-testid="stSidebar"] *  { color:#1a1a2e !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color:#0f3460 !important; }
    [data-testid="stSidebar"] .stButton > button {
        background:linear-gradient(90deg,#e94560,#0f3460);
        color:white !important; font-weight:bold; border:none; border-radius:8px;
    }
    [data-testid="stSidebar"] hr { border-color:#c0c8d8 !important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# 【資料庫模組】
# ════════════════════════════════════════════════════════════════════════
DB_PATH = "scan_history.db"

def init_db():
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
            ticker     TEXT PRIMARY KEY,
            name       TEXT,
            added_date TEXT,
            note       TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_scan_results(df: pd.DataFrame, params: dict):
    conn        = sqlite3.connect(DB_PATH)
    scan_date   = datetime.now().strftime("%Y-%m-%d")
    scan_time   = datetime.now().strftime("%H:%M:%S")
    params_json = json.dumps(params, ensure_ascii=False)
    for _, row in df.iterrows():
        conn.execute("""
            INSERT INTO scan_results
            (scan_date,scan_time,ticker,name,market,score,grade,
             close_price,change_pct,vol_ratio,signal_date,params_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            scan_date, scan_time,
            row.get("代號",""), row.get("公司名稱",""), row.get("市場",""),
            row.get("推薦指數",0), row.get("推薦等級",""),
            row.get("收盤價",0), row.get("漲幅(%)",0),
            row.get("量比(倍)",0), row.get("訊號日期",""),
            params_json
        ))
    conn.commit()
    conn.close()


def load_history(days: int = 30) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn  = sqlite3.connect(DB_PATH)
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df    = pd.read_sql_query(
        "SELECT * FROM scan_results WHERE scan_date >= ? ORDER BY scan_date DESC, score DESC",
        conn, params=(since,)
    )
    conn.close()
    return df


def get_watchlist() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query(
        "SELECT * FROM watchlist ORDER BY added_date DESC", conn
    )
    conn.close()
    return df


def add_to_watchlist(ticker: str, name: str, note: str = ""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO watchlist (ticker,name,added_date,note)
        VALUES (?,?,?,?)
    """, (ticker, name, datetime.now().strftime("%Y-%m-%d"), note))
    conn.commit()
    conn.close()


def remove_from_watchlist(ticker: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════════════════
# 【樣式函式】純 CSS，零 matplotlib 依賴
# ════════════════════════════════════════════════════════════════════════

def _score_to_color(v):
    try:
        t = max(0.0, min(1.0, (float(v)-60)/40))
        return f"background-color:rgb(255,{int(255*(1-t*0.85))},{int(50*(1-t))});color:#1a1a2e;font-weight:bold;"
    except Exception:
        return ""

def _vol_to_color(v):
    try:
        t = max(0.0, min(1.0, (float(v)-2.5)/5.5))
        g = int(220*(1-t))
        return f"background-color:rgb(255,{g},{g});color:#1a1a2e;"
    except Exception:
        return ""

def _chg_to_color(v):
    try:
        f = float(v)
        if f >= 0:
            t = min(1.0, f/10)
            return f"background-color:rgb(50,{int(180+75*t)},50);color:#fff;"
        else:
            t = min(1.0, abs(f)/5)
            return f"background-color:rgb({int(180+75*t)},50,50);color:#fff;"
    except Exception:
        return ""

def _tangle_to_color(v):
    try:
        t  = max(0.0, min(1.0, float(v)/0.05))
        fg = "#fff" if t < 0.5 else "#1a1a2e"
        return (f"background-color:rgb({int(80+175*t)},{int(40+215*t)},{int(160+95*t)});"
                f"color:{fg};")
    except Exception:
        return ""

def _apply_map(styled, func, subset):
    pd_ver = tuple(int(x) for x in pd.__version__.split(".")[:2])
    return styled.map(func, subset=subset) if pd_ver >= (2,1) else styled.applymap(func, subset=subset)

def style_result_df(df: pd.DataFrame):
    def hl_grade(v):
        s = str(v)
        if "S級" in s: return "background-color:#7b2d00;color:#ff9944;font-weight:bold"
        if "A級" in s: return "background-color:#1a3a1a;color:#66ff66;font-weight:bold"
        if "B級" in s: return "background-color:#1a1a3a;color:#8888ff"
        return ""
    def hl_gap(v):
        return "background-color:#2d1a4a;color:#cc88ff;font-weight:bold" if "🚀" in str(v) else "color:#888"

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
        "建議進場價"    : "{:.2f}",
        "停損一(MA10)"  : "{:.2f}",
        "停損二(MA20)"  : "{:.2f}",
        "停利一(+8%)"   : "{:.2f}",
        "停利二(+15%)"  : "{:.2f}",
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styled = df.style
    for col, fn in [("推薦指數",_score_to_color),("量比(倍)",_vol_to_color),
                    ("漲幅(%)",_chg_to_color),("均線糾結度",_tangle_to_color)]:
        if col in df.columns:
            styled = styled.apply(lambda c, f=fn: [f(v) for v in c], subset=[col])
    if "推薦等級"   in df.columns: styled = _apply_map(styled, hl_grade, ["推薦等級"])
    if "有跳空缺口" in df.columns: styled = _apply_map(styled, hl_gap,   ["有跳空缺口"])
    return styled.format(fmt, na_rep="N/A")

def style_score_df(df: pd.DataFrame):
    def sc(v, vmin, vmax, r, g, b):
        try:
            t  = max(0.0, min(1.0, (float(v)-vmin)/max(vmax-vmin,1)))
            fg = "#fff" if t > 0.4 else "#1a1a2e"
            return (f"background-color:rgb({min(255,int(r*t+40))},"
                    f"{min(255,int(g*t+40))},{min(255,int(b*t+40))});color:{fg};")
        except Exception:
            return ""
    fmt = {
        "推薦指數"    :"{} 分","基礎分"      :"{} 分",
        "爆發力加分"  :"+{} 分","籌碼集中加分":"+{} 分",
        "鎖碼強勢加分":"+{} 分","跳空加分"    :"+{} 分",
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styled = df.style
    for col,(vmin,vmax,r,g,b) in {
        "推薦指數"    :(60,100,255,160,  0),
        "爆發力加分"  :( 0, 15,220, 50, 50),
        "籌碼集中加分":( 0, 10,120, 50,200),
        "鎖碼強勢加分":( 0, 10, 50,100,220),
        "跳空加分"    :( 0,  5, 50,180, 80),
    }.items():
        if col in df.columns:
            styled = styled.apply(
                lambda c,vmin=vmin,vmax=vmax,r=r,g=g,b=b:
                    [sc(v,vmin,vmax,r,g,b) for v in c],
                subset=[col]
            )
    return styled.format(fmt, na_rep="N/A")


# ════════════════════════════════════════════════════════════════════════
# 【K 線圖模組】
# ════════════════════════════════════════════════════════════════════════

def plot_candlestick(ticker_yf: str, ticker_name: str, signal_date: str = None):
    if not PLOTLY_OK:
        st.warning("請在 requirements.txt 加入 plotly。")
        return
    try:
        df = yf.download(ticker_yf, period="3mo", auto_adjust=True, progress=False)
        if df.empty:
            st.warning(f"無法取得 {ticker_yf} 資料。")
            return
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        df["MA5"]  = df["Close"].rolling(5).mean()
        df["MA10"] = df["Close"].rolling(10).mean()
        df["MA20"] = df["Close"].rolling(20).mean()

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.05, row_heights=[0.7, 0.3]
        )
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name="K線",
            increasing_line_color="#e94560", decreasing_line_color="#00b894",
            increasing_fillcolor="#e94560",  decreasing_fillcolor="#00b894",
        ), row=1, col=1)

        for ma, color in [("MA5","#ffaa44"),("MA10","#74b9ff"),("MA20","#a29bfe")]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[ma], name=ma,
                line=dict(color=color, width=1.5),
            ), row=1, col=1)

        if signal_date:
            try:
                sig_dt = pd.to_datetime(signal_date)
                if sig_dt in df.index:
                    fig.add_trace(go.Scatter(
                        x=[sig_dt], y=[df.loc[sig_dt,"Low"]*0.97],
                        mode="markers+text",
                        marker=dict(symbol="triangle-up", size=16, color="#e94560"),
                        text=["訊號"], textposition="bottom center",
                        textfont=dict(color="#e94560", size=11),
                        name="訊號日",
                    ), row=1, col=1)
            except Exception:
                pass

        colors = [
            "#e94560" if c >= o else "#00b894"
            for c, o in zip(df["Close"], df["Open"])
        ]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="成交量", marker_color=colors,
        ), row=2, col=1)

        code = ticker_yf.replace(".TW","").replace(".TWO","")
        fig.update_layout(
            title=f"📈 {code} {ticker_name}  近 3 個月 K 線",
            title_font=dict(color="#e94560", size=16),
            paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
            font=dict(color="#a8b2d8"),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
            height=520, margin=dict(l=10,r=10,t=60,b=10),
        )
        fig.update_xaxes(gridcolor="#1e2a3a",
                         rangebreaks=[dict(bounds=["sat","mon"])])
        fig.update_yaxes(gridcolor="#1e2a3a")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"K 線圖繪製失敗：{e}")


# ════════════════════════════════════════════════════════════════════════
# 【停損停利計算器】
# ════════════════════════════════════════════════════════════════════════

def calculate_tp_sl(row: dict) -> dict:
    c    = row.get("收盤價", 0)
    ma10 = row.get("MA10",  c * 0.97)
    ma20 = row.get("MA20",  c * 0.94)
    entry  = round(c * 1.005, 2)
    sl1    = round(ma10, 2)
    sl2    = round(ma20, 2)
    tp1    = round(entry * 1.08, 2)
    tp2    = round(entry * 1.15, 2)
    risk   = entry - sl1
    rr     = round((tp1 - entry) / risk, 2) if risk > 0 else None
    return {
        "建議進場價"  : entry,
        "停損一(MA10)": sl1,
        "停損二(MA20)": sl2,
        "停利一(+8%)" : tp1,
        "停利二(+15%)": tp2,
        "風報比"      : rr,
    }


# ════════════════════════════════════════════════════════════════════════
# 【Discord 推播】
# ════════════════════════════════════════════════════════════════════════

def send_discord(webhook_url: str, df_s: pd.DataFrame, scan_time: str):
    if not webhook_url or df_s.empty:
        return False, "無 Webhook URL 或無 S 級標的"

    embeds = [{
        "title"      : "🏆 台股選股器 v6.0 掃描結果",
        "description": f"📅 {scan_time}\n🔥 S 級強烈推薦：**{len(df_s)} 檔**",
        "color"      : 0xe94560,
    }]

    for _, row in df_s.head(10).iterrows():
        chg    = row.get("漲幅(%)", 0)
        tp_sl  = calculate_tp_sl(row.to_dict())
        embeds.append({
            "title": f"🔥 {row['代號']} {row.get('公司名稱','')}",
            "color": 0xff6b35,
            "fields": [
                {"name":"推薦指數",   "value":f"**{row['推薦指數']} 分**",        "inline":True},
                {"name":"收盤價",     "value":f"**{row['收盤價']:.2f} 元**",      "inline":True},
                {"name":"漲幅",       "value":f"{'▲' if chg>=0 else '▼'}{abs(chg):.2f}%","inline":True},
                {"name":"量比",       "value":f"{row['量比(倍)']:.2f}x",          "inline":True},
                {"name":"建議進場",   "value":f"{tp_sl['建議進場價']:.2f}",        "inline":True},
                {"name":"停損(MA10)", "value":f"{tp_sl['停損一(MA10)']:.2f}",     "inline":True},
                {"name":"風報比",     "value":str(tp_sl['風報比']),               "inline":True},
                {"name":"市場",       "value":row.get("市場",""),                 "inline":True},
                {"name":"訊號日期",   "value":row.get("訊號日期",""),             "inline":True},
            ],
        })

    try:
        res = requests.post(webhook_url, json={"embeds": embeds}, timeout=10, verify=False)
        if res.status_code in (200, 204):
            return True, "✅ 推播成功！"
        return False, f"推播失敗：HTTP {res.status_code}"
    except Exception as e:
        return False, f"推播失敗：{e}"


# ════════════════════════════════════════════════════════════════════════
# 【回測模組】
# ════════════════════════════════════════════════════════════════════════

def run_backtest(ticker_yf: str, ticker_name: str, params: dict, hold_days: int = 10):
    try:
        df = yf.download(ticker_yf, period="2y", auto_adjust=True, progress=False)
        if df.empty or len(df) < 60:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
    except Exception:
        return None

    p = params
    df["avg_vol_5"] = df["Volume"].shift(1).rolling(p["vol_window"]).mean()
    df["high_20"]   = df["High"].shift(1).rolling(p["high_window"]).max()
    df["ma5"]       = df["Close"].rolling(p["ma_fast"]).mean()
    df["ma10"]      = df["Close"].rolling(p["ma_slow"]).mean()
    df["ma20"]      = df["Close"].rolling(p["ma_month"]).mean()
    cr              = df["High"] - df["Low"]
    df["body_pct"]  = (df["Close"] - df["Low"]) / cr.replace(0, float("nan"))

    df_bt  = df[df.index >= datetime.now() - timedelta(days=365)].copy()
    trades = []

    for i in range(1, len(df_bt) - hold_days):
        r  = df_bt.iloc[i]
        pv = df_bt.iloc[i-1]
        c=r["Close"]; o=r["Open"]; v=r["Volume"]
        avg=r["avg_vol_5"]; h20=r["high_20"]
        ma5=r["ma5"]; ma10=r["ma10"]; ma20=r["ma20"]
        bp=r["body_pct"]; pma20=pv["ma20"]

        conds = [
            c >= p["min_price"],
            pd.notna(avg) and avg > p["liquidity_vol"],
            pd.notna(avg) and v > avg * p["vol_multiplier"],
            pd.notna(h20) and c >= h20,
            c > o and pd.notna(bp) and bp >= p["body_ratio"],
            pd.notna(ma5) and pd.notna(ma10) and c > ma5 > ma10,
            pd.notna(ma20) and pd.notna(pma20) and c > ma20 and ma20 >= pma20,
        ]
        if not all(conds):
            continue

        entry = df_bt.iloc[i+1]["Open"]
        exit_ = df_bt.iloc[i+hold_days]["Close"]
        ret   = (exit_ - entry) / entry * 100
        trades.append({
            "訊號日期" : df_bt.index[i].strftime("%Y-%m-%d"),
            "進場價"   : round(entry, 2),
            "出場價"   : round(exit_, 2),
            "報酬率(%)": round(ret,   2),
            "結果"     : "✅ 獲利" if ret > 0 else "❌ 虧損",
        })

    if not trades:
        return None

    df_t = pd.DataFrame(trades)
    rets = df_t["報酬率(%)"]
    return {
        "代號"       : ticker_yf.replace(".TW","").replace(".TWO",""),
        "名稱"       : ticker_name,
        "訊號次數"   : len(trades),
        "勝率(%)"    : round(len(rets[rets>0])/len(rets)*100, 1),
        "平均報酬(%)": round(rets.mean(), 2),
        "最大獲利(%)": round(rets.max(),  2),
        "最大虧損(%)": round(rets.min(),  2),
        "trades"     : df_t,
    }


# ════════════════════════════════════════════════════════════════════════
# 【評分計算】
# ════════════════════════════════════════════════════════════════════════

def calculate_recommendation_score(vol_ratio, tangle_val, body_pct, is_gap_up, cfg):
    bd = {"基礎分": cfg["base_score"]}

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
# 【選股策略】
# ════════════════════════════════════════════════════════════════════════

def _base_prep(ticker, df, params):
    """共用資料前處理，回傳清洗後的 df 或 None。"""
    p = params
    required = ["Open","High","Low","Close","Volume"]
    if not all(c in df.columns for c in required):
        return None
    df = df[required].copy().dropna(subset=["Close","Volume"])
    before = len(df)
    df = df[df["Volume"] > 0]
    if before > 0 and (before-len(df))/before > 0.20:
        return None
    if len(df) < p["min_bars"]:
        return None
    last_date = df.index[-1]
    if hasattr(last_date,"tzinfo") and last_date.tzinfo is not None:
        last_date = last_date.tz_localize(None)
    if (datetime.now()-last_date).days > p["max_days_stale"]:
        return None
    return df


def apply_filter_v5(ticker, df, params, cfg):
    """爆量突破策略（原版）。"""
    p  = params
    df = _base_prep(ticker, df, params)
    if df is None:
        return None

    df["avg_vol_5"] = df["Volume"].shift(1).rolling(p["vol_window"]).mean()
    df["high_20"]   = df["High"].shift(1).rolling(p["high_window"]).max()
    df["ma5"]       = df["Close"].rolling(p["ma_fast"]).mean()
    df["ma10"]      = df["Close"].rolling(p["ma_slow"]).mean()
    df["ma20"]      = df["Close"].rolling(p["ma_month"]).mean()
    cr              = df["High"] - df["Low"]
    df["body_pct"]  = (df["Close"]-df["Low"]) / cr.replace(0, float("nan"))
    stk = pd.concat([df["ma5"].shift(1), df["ma10"].shift(1), df["ma20"].shift(1)], axis=1)
    df["ma_tangle"] = (stk.max(axis=1)-stk.min(axis=1)) / stk.min(axis=1).replace(0, float("nan"))

    if len(df) < 2:
        return None
    last=df.iloc[-1]; prev=df.iloc[-2]
    o=last["Open"]; l=last["Low"]; c=last["Close"]; v=last["Volume"]
    avg=last["avg_vol_5"]; h20=last["high_20"]
    ma5=last["ma5"]; ma10=last["ma10"]; ma20=last["ma20"]; pma20=prev["ma20"]
    bp=last["body_pct"]; tangle=last["ma_tangle"]
    ph=prev["High"]; pc=prev["Close"]

    conds = [
        c >= p["min_price"],
        pd.notna(avg) and avg > p["liquidity_vol"],
        pd.notna(avg) and v > avg*p["vol_multiplier"],
        pd.notna(h20) and c >= h20,
        c > o and pd.notna(bp) and bp >= p["body_ratio"],
        pd.notna(ma5) and pd.notna(ma10) and c > ma5 > ma10,
        pd.notna(ma20) and pd.notna(pma20) and c > ma20 and ma20 >= pma20,
    ]
    if not all(conds):
        return None

    vol_ratio = v/avg if avg > 0 else 0
    is_gap_up = (l > ph) if pd.notna(ph) else False
    score, bd = calculate_recommendation_score(vol_ratio, tangle, bp, is_gap_up, cfg)
    grade     = get_grade_label(score, cfg)
    tp_sl     = calculate_tp_sl({"收盤價":c,"MA10":ma10,"MA20":ma20})

    return {
        "代號"          : ticker.replace(".TW","").replace(".TWO",""),
        "YF代號"        : ticker,
        "策略"          : "🔥 爆量突破",
        "推薦指數"      : score,
        "推薦等級"      : grade,
        "基礎分"        : bd["基礎分"],
        "爆發力加分"    : bd["爆發力"],
        "籌碼集中加分"  : bd["籌碼集中"],
        "鎖碼強勢加分"  : bd["鎖碼強勢"],
        "跳空加分"      : bd["跳空表態"],
        "收盤價"        : round(c,2),
        "漲幅(%)"       : round((c-pc)/pc*100 if pc>0 else 0, 2),
        "量比(倍)"      : round(vol_ratio, 2),
        "當日量(張)"    : int(v/1000),
        "5日均量(張)"   : int(avg/1000),
        "MA5"           : round(ma5,2),
        "MA10"          : round(ma10,2),
        "MA20"          : round(ma20,2),
        "月線斜率(%)"   : round((ma20-pma20)/pma20*100 if pma20>0 else 0, 3),
        "距月線乖離(%)" : round((c-ma20)/ma20*100 if ma20>0 else 0, 2),
        "實體比例"      : round(bp,3),
        "均線糾結度"    : round(tangle,4) if pd.notna(tangle) else None,
        "跳空缺口(%)"   : round((o-pc)/pc*100 if pc>0 else 0, 2),
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
    """低檔翻揚策略。"""
    p  = params
    df = _base_prep(ticker, df, params)
    if df is None:
        return None

    df["avg_vol_5"] = df["Volume"].shift(1).rolling(5).mean()
    df["low_60"]    = df["Low"].rolling(60).min()
    df["ma5"]       = df["Close"].rolling(5).mean()
    df["ma20"]      = df["Close"].rolling(20).mean()
    df["ma5_prev"]  = df["ma5"].shift(1)
    df["ma20_prev"] = df["ma20"].shift(1)

    if len(df) < 2:
        return None
    last=df.iloc[-1]; prev=df.iloc[-2]
    c=last["Close"]; o=last["Open"]; v=last["Volume"]
    avg=last["avg_vol_5"]; low60=last["low_60"]
    ma5=last["ma5"]; ma20=last["ma20"]
    ma5p=last["ma5_prev"]; ma20p=last["ma20_prev"]
    pc=prev["Close"]

    conds = [
        c >= p["min_price"],
        pd.notna(avg) and avg > p["liquidity_vol"],
        pd.notna(avg) and v > avg*2.0,
        c > o,
        pd.notna(low60) and (c-low60)/low60 < 0.15,
        pd.notna(ma5) and pd.notna(ma20),
        ma5 > ma20 and ma5p <= ma20p,
    ]
    if not all(conds):
        return None

    vol_ratio = v/avg if avg > 0 else 0
    tp_sl     = calculate_tp_sl({"收盤價":c,"MA10":ma5,"MA20":ma20})
    return {
        "代號"         : ticker.replace(".TW","").replace(".TWO",""),
        "YF代號"       : ticker,
        "策略"         : "📉 低檔翻揚",
        "推薦指數"     : 70,
        "推薦等級"     : "⭐ A級｜推薦",
        "收盤價"       : round(c,2),
        "漲幅(%)"      : round((c-pc)/pc*100 if pc>0 else 0, 2),
        "量比(倍)"     : round(vol_ratio,2),
        "MA5"          : round(ma5,2),
        "MA20"         : round(ma20,2),
        "建議進場價"   : tp_sl["建議進場價"],
        "停損一(MA10)" : tp_sl["停損一(MA10)"],
        "停損二(MA20)" : tp_sl["停損二(MA20)"],
        "停利一(+8%)"  : tp_sl["停利一(+8%)"],
        "停利二(+15%)" : tp_sl["停利二(+15%)"],
        "風報比"       : tp_sl["風報比"],
        "訊號日期"     : df.index[-1].strftime("%Y-%m-%d"),
    }


def apply_filter_tangle(ticker, df, params, cfg):
    """均線糾結爆發策略。"""
    p  = params
    df = _base_prep(ticker, df, params)
    if df is None:
        return None

    df["avg_vol_5"] = df["Volume"].shift(1).rolling(5).mean()
    df["ma5"]       = df["Close"].rolling(5).mean()
    df["ma10"]      = df["Close"].rolling(10).mean()
    df["ma20"]      = df["Close"].rolling(20).mean()
    stk = pd.concat([df["ma5"].shift(1), df["ma10"].shift(1), df["ma20"].shift(1)], axis=1)
    df["tangle_prev"] = (stk.max(axis=1)-stk.min(axis=1)) / stk.min(axis=1).replace(0, float("nan"))

    if len(df) < 2:
        return None
    last=df.iloc[-1]; prev=df.iloc[-2]
    c=last["Close"]; o=last["Open"]; v=last["Volume"]
    avg=last["avg_vol_5"]
    ma5=last["ma5"]; ma10=last["ma10"]; ma20=last["ma20"]
    tangle=last["tangle_prev"]; pc=prev["Close"]
    ma_max = max(x for x in [ma5,ma10,ma20] if pd.notna(x))

    conds = [
        c >= p["min_price"],
        pd.notna(avg) and avg > p["liquidity_vol"],
        pd.notna(avg) and v > avg*3.0,
        c > o,
        pd.notna(tangle) and tangle < 0.02,
        c > ma_max,
    ]
    if not all(conds):
        return None

    vol_ratio = v/avg if avg > 0 else 0
    tp_sl     = calculate_tp_sl({"收盤價":c,"MA10":ma10,"MA20":ma20})
    return {
        "代號"         : ticker.replace(".TW","").replace(".TWO",""),
        "YF代號"       : ticker,
        "策略"         : "🌙 均線糾結爆發",
        "推薦指數"     : 80,
        "推薦等級"     : "⭐ A級｜推薦",
        "收盤價"       : round(c,2),
        "漲幅(%)"      : round((c-pc)/pc*100 if pc>0 else 0, 2),
        "量比(倍)"     : round(vol_ratio,2),
        "均線糾結度"   : round(tangle,4),
        "MA5"          : round(ma5,2),
        "MA10"         : round(ma10,2),
        "MA20"         : round(ma20,2),
        "建議進場價"   : tp_sl["建議進場價"],
        "停損一(MA10)" : tp_sl["停損一(MA10)"],
        "停損二(MA20)" : tp_sl["停損二(MA20)"],
        "停利一(+8%)"  : tp_sl["停利一(+8%)"],
        "停利二(+15%)" : tp_sl["停利二(+15%)"],
        "風報比"       : tp_sl["風報比"],
        "訊號日期"     : df.index[-1].strftime("%Y-%m-%d"),
    }


def apply_strategy(strategy, ticker, df, params, cfg):
    if strategy == "🔥 爆量突破（原版）":
        return apply_filter_v5(ticker, df, params, cfg)
    elif strategy == "📉 低檔翻揚":
        return apply_filter_reversal(ticker, df, params, cfg)
    elif strategy == "🌙 均線糾結爆發":
        return apply_filter_tangle(ticker, df, params, cfg)
    return None


# ════════════════════════════════════════════════════════════════════════
# 【股票清單 + 下載】
# ════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_all_stocks() -> pd.DataFrame:
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    df_twse = pd.DataFrame()
    try:
        res = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            headers=headers, timeout=15, verify=False
        )
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
        res = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
            headers=headers, timeout=15, verify=False
        )
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
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["代號"]).reset_index(drop=True)


def download_all_data(stock_list, lookback_days, batch_size, progress_bar, status_text):
    end_str   = datetime.today().strftime("%Y-%m-%d")
    start_str = (datetime.today()-timedelta(days=int(lookback_days*1.5))).strftime("%Y-%m-%d")
    batches   = [stock_list[i:i+batch_size] for i in range(0,len(stock_list),batch_size)]
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

    # ── 側邊欄 ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚙️ 策略參數調整")
        st.markdown("---")

        st.markdown("### 🎯 選股策略")
        strategy = st.selectbox(
            "選擇策略",
            ["🔥 爆量突破（原版）","📉 低檔翻揚","🌙 均線糾結爆發"],
        )

        st.markdown("### 📊 掃描範圍")
        market_choice = st.radio(
            "掃描市場",
            ["🏢 上市 + 上櫃（全市場）","🏢 僅上市（TWSE）","🏪 僅上櫃（TPEx）"],
        )
        lite_mode     = st.toggle("⚡ 輕量模式（雲端推薦）", value=True)
        lookback_days = st.slider("歷史資料天數", 45, 90, 60, 5)
        batch_size    = st.slider("批次下載大小", 20, 100, 50, 10)

        st.markdown("---")
        st.markdown("### 🛡️ 基礎過濾條件")
        min_price      = st.slider("最低股價（元）",     5,   50,  15,  5)
        liquidity_vol  = st.slider("最低流動性（張）", 100, 2000, 500, 100)
        vol_multiplier = st.slider("爆量倍數",          1.5,  5.0, 2.5, 0.5)
        body_ratio     = st.slider("實體K棒比例",       0.50, 0.95, 0.75, 0.05)
        max_days_stale = st.slider("資料新鮮度（天）",    1,    7,   3,   1)

        st.markdown("---")
        st.markdown("### 🏆 推薦等級門檻")
        grade_s_min = st.slider("S級門檻", 70, 95, 85, 5)
        grade_a_min = st.slider("A級門檻", 60, 84, 70, 5)

        st.markdown("---")
        st.markdown("### 🔔 Discord 推播")
        discord_url = st.text_input(
            "Webhook URL",
            placeholder="https://discord.com/api/webhooks/...",
            type="password",
        )

        st.markdown("---")
        scan_button = st.button("🚀 開始全市場掃描", type="primary", use_container_width=True)

        st.markdown("---")
        st.markdown(
            "<div style='font-size:0.8rem;text-align:center;color:#555;'>"
            "台股選股器 v6.0<br>⚠️ 僅供技術分析參考<br>不構成任何投資建議</div>",
            unsafe_allow_html=True
        )

    # ── 整合參數 ────────────────────────────────────────────────────
    PARAMS = {
        "liquidity_vol" : liquidity_vol * 1000,
        "vol_window"    : 5,
        "vol_multiplier": vol_multiplier,
        "high_window"   : 20,
        "body_ratio"    : body_ratio,
        "ma_fast"       : 5,
        "ma_slow"       : 10,
        "ma_month"      : 20,
        "min_bars"      : 35,
        "min_price"     : min_price,
        "max_days_stale": max_days_stale,
    }
    SCORE_CONFIG = {
        "base_score"            : 60,
        "vol_tier_high_min"     : 5.0,  "vol_tier_high_score"    : 15,
        "vol_tier_mid_min"      : 3.0,  "vol_tier_mid_score"     : 10,
        "vol_tier_low_min"      : 2.5,  "vol_tier_low_score"     : 5,
        "tangle_tier_high_max"  : 0.03, "tangle_tier_high_score" : 10,
        "tangle_tier_mid_max"   : 0.05, "tangle_tier_mid_score"  : 5,
        "body_tier_high_min"    : 0.95, "body_tier_high_score"   : 10,
        "body_tier_mid_min"     : 0.85, "body_tier_mid_score"    : 5,
        "gap_up_score"          : 5,
        "grade_s_min"           : grade_s_min,
        "grade_a_min"           : grade_a_min,
        "grade_b_min"           : 60,
    }

    # ════════════════════════════════════════════════════════════════
    # 主頁面分頁（掃描前顯示說明 + 歷史 + 追蹤清單）
    # ════════════════════════════════════════════════════════════════
    if not scan_button:
        tab_home, tab_history, tab_watch = st.tabs(["🏠 首頁說明","📅 歷史紀錄","👁️ 追蹤清單"])

        with tab_home:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### 📋 選股條件說明")
                st.markdown("""
| # | 條件 | 說明 |
|---|------|------|
| 1 | 🛡️ 非低價股 | 股價 ≥ 設定門檻 |
| 2 | 💧 流動性 | 近5日均量 > N 張 |
| 3 | 💥 爆量突破 | 當日量 > 均量 × N 倍 |
| 4 | 📈 創20日新高 | 收盤突破前20日高點 |
| 5 | 🕯️ 實體紅K | 收盤接近最高價 |
| 6 | 📊 均線多頭 | 收盤 > MA5 > MA10 |
| 7 | 🌙 月線翻多 | 站上MA20且月線向上 |
                """)
            with c2:
                st.markdown("### 🎯 策略說明")
                st.markdown("""
| 策略 | 核心邏輯 | 適合情境 |
|------|---------|---------|
| 🔥 爆量突破 | 量增價漲突破新高 | 多頭趨勢中 |
| 📉 低檔翻揚 | 低點反彈MA黃金交叉 | 底部反轉 |
| 🌙 均線糾結 | 三線糾結後爆量突破 | 盤整後爆發 |
                """)
                st.markdown("### 🏆 推薦指數架構")
                st.markdown("""
| 項目 | 最高分 | 條件 |
|------|--------|------|
| 基礎分 | 60分 | 通過全部條件 |
| 爆發力 | 15分 | 量比 ≥ 5倍 |
| 籌碼集中 | 10分 | 三線差距 < 3% |
| 鎖碼強勢 | 10分 | 實體比例 ≥ 95% |
| 跳空表態 | 5分 | 今低 > 昨高 |
                """)
            st.info("👈 請在左側調整參數後，點擊『🚀 開始全市場掃描』。")
            st.warning("⏰ 建議台股收盤後（13:35後）執行，確保資料完整。")

        with tab_history:
            st.markdown("### 📅 歷史掃描紀錄")
            days_back = st.slider("查看最近幾天", 7, 90, 30, 7)
            df_hist   = load_history(days_back)
            if df_hist.empty:
                st.info("尚無歷史紀錄，掃描後會自動儲存。")
            else:
                st.metric("歷史訊號總數", f"{len(df_hist)} 筆")
                # 勝率統計（需有後續資料）
                st.dataframe(
                    df_hist[["scan_date","ticker","name","market",
                              "score","grade","close_price","change_pct","signal_date"]],
                    use_container_width=True, height=400
                )
                # 出現頻率排行
                st.markdown("#### 🏆 出現頻率排行（重複出現代表持續強勢）")
                freq = df_hist.groupby(["ticker","name"]).size().reset_index(name="出現次數")
                freq = freq.sort_values("出現次數", ascending=False).head(20)
                st.dataframe(freq, use_container_width=True)

        with tab_watch:
            st.markdown("### 👁️ 追蹤清單")
            df_wl = get_watchlist()
            if df_wl.empty:
                st.info("追蹤清單為空，掃描後可從結果頁加入。")
            else:
                st.dataframe(df_wl, use_container_width=True)
                rm_ticker = st.text_input("輸入代號移除追蹤")
                if st.button("🗑️ 移除") and rm_ticker:
                    remove_from_watchlist(rm_ticker.upper())
                    st.success(f"已移除 {rm_ticker}")
                    st.rerun()

                # 追蹤清單 K 線預覽
                if PLOTLY_OK and not df_wl.empty:
                    st.markdown("#### 📈 追蹤標的 K 線")
                    sel = st.selectbox(
                        "選擇標的查看 K 線",
                        df_wl["ticker"].tolist()
                    )
                    if sel:
                        name = df_wl[df_wl["ticker"]==sel]["name"].values[0]
                        plot_candlestick(sel, name)
        return

    # ════════════════════════════════════════════════════════════════
    # 【掃描流程】
    # ════════════════════════════════════════════════════════════════

    # 步驟一：取得清單
    with st.status("📋 步驟 1/3：抓取全台股清單...", expanded=True) as status:
        df_all_stocks = get_all_stocks()
        if df_all_stocks.empty:
            st.error("❌ 無法取得股票清單。")
            return
        if "僅上市" in market_choice:
            df_all_stocks = df_all_stocks[df_all_stocks["市場"] == "上市(TWSE)"]
        elif "僅上櫃" in market_choice:
            df_all_stocks = df_all_stocks[df_all_stocks["市場"] == "上櫃(TPEx)"]

        if lite_mode:
            df_all_stocks = df_all_stocks.head(300)
            st.info("⚡ 輕量模式：掃描前 300 檔。")

        total_stocks = len(df_all_stocks)
        st.write(f"✅ 取得 **{total_stocks:,}** 檔股票代號")
        status.update(label=f"✅ 步驟 1/3 完成：取得 {total_stocks:,} 檔", state="complete")

    # 步驟二：批次下載
    with st.status("📥 步驟 2/3：批次下載歷史資料...", expanded=True) as status:
        progress_bar = st.progress(0, text="準備下載...")
        status_text  = st.empty()
        all_data = download_all_data(
            df_all_stocks["YF代號"].tolist(),
            lookback_days, batch_size, progress_bar, status_text,
        )
        progress_bar.progress(1.0, text="✅ 下載完成！")
        status_text.empty()
        success_count = len(all_data)
        st.write(f"✅ 成功下載 **{success_count:,}** 檔")
        status.update(label=f"✅ 步驟 2/3 完成：下載 {success_count:,} 檔", state="complete")

    # 步驟三：選股評分
    with st.status("🔍 步驟 3/3：執行選股與評分...", expanded=True) as status:
        market_map    = dict(zip(df_all_stocks["YF代號"], df_all_stocks["市場"]))
        name_map      = dict(zip(df_all_stocks["YF代號"], df_all_stocks["名稱"]))
        results       = []
        ticker_list   = list(all_data.items())
        scan_total    = len(ticker_list)
        scan_progress = st.progress(0, text="選股掃描中...")

        for i, (ticker, df_stock) in enumerate(ticker_list):
            if i % 50 == 0:
                scan_progress.progress(
                    (i+1)/scan_total,
                    text=f"🔎 掃描中... {i+1}/{scan_total}（已找到 {len(results)} 個）"
                )
            try:
                result = apply_strategy(strategy, ticker, df_stock.copy(), PARAMS, SCORE_CONFIG)
                if result:
                    result["公司名稱"] = name_map.get(ticker, "")
                    result["市場"]     = market_map.get(ticker, "")
                    results.append(result)
            except Exception:
                pass

        scan_progress.progress(1.0, text="✅ 掃描完成！")
        st.write(f"✅ 掃描完成！共 **{len(results)}** 檔符合條件")
        status.update(label=f"✅ 步驟 3/3 完成：找到 {len(results)} 個符合標的", state="complete")

    # ════════════════════════════════════════════════════════════════
    # 【結果處理】
    # ════════════════════════════════════════════════════════════════
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    if not results:
        st.warning("📭 今日無標的符合所有條件。")
        st.markdown("""
**🔧 建議放寬以下參數後重新掃描：**
- 爆量倍數 → **2.0**
- 實體比例 → **0.65**
- 最低股價 → **10 元**
        """)
        return

    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values(
        ["推薦指數","量比(倍)"], ascending=[False,False]
    ).reset_index(drop=True)
    df_result.index += 1

    # 儲存到資料庫
    save_scan_results(df_result, PARAMS)

    df_s = df_result[df_result["推薦指數"] >= SCORE_CONFIG["grade_s_min"]]
    df_a = df_result[
        (df_result["推薦指數"] >= SCORE_CONFIG["grade_a_min"]) &
        (df_result["推薦指數"] <  SCORE_CONFIG["grade_s_min"])
    ]
    df_b = df_result[df_result["推薦指數"] < SCORE_CONFIG["grade_a_min"]]

    # ── Discord 推播 ─────────────────────────────────────────────────
    scan_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if discord_url:
        ok, msg = send_discord(discord_url, df_s, scan_time_str)
        if ok:
            st.success(f"🔔 {msg}")
        else:
            st.warning(f"🔔 {msg}")

    # ── Metric 卡片 ──────────────────────────────────────────────────
    st.markdown(f"### 📊 掃描結果摘要 — {scan_time_str}　｜　策略：{strategy}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📊 掃描總檔數",  f"{success_count:,} 檔")
    m2.metric("✅ 符合條件",    f"{len(df_result)} 檔",
              delta=f"通過率 {len(df_result)/success_count*100:.2f}%")
    m3.metric("🔥 S級強烈推薦", f"{len(df_s)} 檔",  delta=f"≥ {grade_s_min} 分")
    m4.metric("⭐ A級推薦",     f"{len(df_a)} 檔",  delta=f"{grade_a_min}~{grade_s_min-1} 分")
    m5.metric("👀 B級觀察",     f"{len(df_b)} 檔",  delta=f"60~{grade_a_min-1} 分")

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════
    # 【主要結果分頁】
    # ════════════════════════════════════════════════════════════════
    tab_result, tab_kline, tab_tpsl, tab_backtest, tab_watch_add = st.tabs([
        "📊 選股結果",
        "📈 K 線預覽",
        "🎯 停損停利",
        "🔬 回測驗證",
        "👁️ 加入追蹤",
    ])

    # ── 欄位定義 ────────────────────────────────────────────────────
    detail_cols = [
        "代號","公司名稱","市場","策略",
        "推薦指數","推薦等級",
        "收盤價","漲幅(%)","量比(倍)",
        "當日量(張)","5日均量(張)",
        "MA5","MA10","MA20",
        "月線斜率(%)","距月線乖離(%)",
        "實體比例","均線糾結度",
        "跳空缺口(%)","有跳空缺口",
        "建議進場價","停損一(MA10)","停損二(MA20)",
        "停利一(+8%)","停利二(+15%)","風報比",
        "訊號日期",
    ]
    detail_cols = [c for c in detail_cols if c in df_result.columns]

    def show_tab(df_sub):
        if df_sub.empty:
            st.info("此等級無符合標的。")
            return
        d = df_sub[detail_cols].reset_index(drop=True)
        d.index += 1
        st.dataframe(style_result_df(d), use_container_width=True,
                     height=min(600, 50+len(d)*38))

    # ════════════════════════════════════════════════════════════════
    # 分頁一：選股結果
    # ════════════════════════════════════════════════════════════════
    with tab_result:
        # S 級卡片
        st.markdown(f"## 🔥 核心推薦標的（S 級 ≥ {grade_s_min} 分）")
        if df_s.empty:
            st.info(
                f"今日無 S 級標的。最高分：**{df_result.iloc[0]['代號']}** "
                f"{df_result.iloc[0].get('公司名稱','')} — "
                f"**{df_result.iloc[0]['推薦指數']} 分**"
            )
        else:
            s_list = df_s.reset_index(drop=True)
            for row_start in range(0, len(s_list), 3):
                cols = st.columns(3)
                for ci in range(3):
                    idx = row_start + ci
                    if idx >= len(s_list):
                        break
                    row = s_list.iloc[idx]
                    chg_color = "#ff4444" if row["漲幅(%)"] >= 0 else "#44ff44"
                    with cols[ci]:
                        st.markdown(f"""
<div class="stock-card">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
            <span class="ticker">{row['代號']}</span>
            <span class="name"> {row.get('公司名稱','')}</span><br>
            <small style="color:#aaa">{row.get('市場','')} | {row.get('訊號日期','')}</small>
        </div>
        <div class="score">{row['推薦指數']}<small style="font-size:0.8rem">分</small></div>
    </div>
    <hr style="border-color:#2d3561;margin:0.5rem 0">
    <div style="display:flex;justify-content:space-between;">
        <span class="price">💰 {row['收盤價']:.2f} 元</span>
        <span style="color:{chg_color}">{'▲' if row['漲幅(%)']>=0 else '▼'} {abs(row['漲幅(%)']):+.2f}%</span>
        <span style="color:#ffaa44">📊 {row['量比(倍)']:.2f}x</span>
    </div>
</div>
                        """, unsafe_allow_html=True)

        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
        st.markdown("## 📊 完整評分詳細表")

        inner_tabs = st.tabs([
            f"🔢 全部（{len(df_result)}）",
            f"🔥 S級（{len(df_s)}）",
            f"⭐ A級（{len(df_a)}）",
            f"👀 B級（{len(df_b)}）",
            "🔬 加分明細",
        ])
        with inner_tabs[0]: show_tab(df_result)
        with inner_tabs[1]: show_tab(df_s)
        with inner_tabs[2]: show_tab(df_a)
        with inner_tabs[3]: show_tab(df_b)
        with inner_tabs[4]:
            sc_cols = ["代號","公司名稱","推薦指數","基礎分",
                       "爆發力加分","籌碼集中加分","鎖碼強勢加分","跳空加分"]
            sc_cols = [c for c in sc_cols if c in df_result.columns]
            df_sc   = df_result[sc_cols].reset_index(drop=True)
            df_sc.index += 1
            st.dataframe(style_score_df(df_sc), use_container_width=True,
                         height=min(600, 50+len(df_sc)*38))

        # 統計圖表
        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
        st.markdown("## 📈 統計分析")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 推薦等級分佈")
            st.bar_chart(
                pd.DataFrame({"標的數":[len(df_s),len(df_a),len(df_b)]},
                             index=["🔥 S級","⭐ A級","👀 B級"]),
                color="#e94560"
            )
        with c2:
            st.markdown("#### 市場分佈")
            mc = df_result["市場"].value_counts().reset_index()
            mc.columns = ["市場","標的數"]
            st.bar_chart(mc.set_index("市場"), color="#0f3460")

        # CSV 下載
        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
        st.markdown("## 💾 下載結果")
        today_file = datetime.now().strftime("%Y%m%d_%H%M")
        dl1, dl2   = st.columns(2)
        with dl1:
            st.download_button(
                "📥 下載完整結果 CSV",
                data=df_result.to_csv(encoding="utf-8-sig", index=True),
                file_name=f"台股選股_v6_{today_file}.csv",
                mime="text/csv", use_container_width=True,
            )
        with dl2:
            if not df_s.empty:
                st.download_button(
                    "🔥 下載 S 級推薦 CSV",
                    data=df_s.to_csv(encoding="utf-8-sig", index=True),
                    file_name=f"台股S級推薦_v6_{today_file}.csv",
                    mime="text/csv", use_container_width=True,
                )

    # ════════════════════════════════════════════════════════════════
    # 分頁二：K 線預覽
    # ════════════════════════════════════════════════════════════════
    with tab_kline:
        st.markdown("### 📈 個股 K 線互動預覽")
        if not PLOTLY_OK:
            st.warning("請在 requirements.txt 加入 `plotly` 套件。")
        else:
            ticker_options = [
                f"{r['代號']} {r.get('公司名稱','')} ({r['推薦指數']}分)"
                for _, r in df_result.iterrows()
            ]
            selected = st.selectbox("選擇股票查看 K 線", ticker_options)
            if selected:
                code     = selected.split(" ")[0]
                row_data = df_result[df_result["代號"] == code].iloc[0]
                yf_code  = row_data["YF代號"]
                name     = row_data.get("公司名稱","")
                sig_date = row_data.get("訊號日期","")

                # 停損停利資訊
                tp_sl = calculate_tp_sl(row_data.to_dict())
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("建議進場",   f"{tp_sl['建議進場價']:.2f}")
                c2.metric("停損一 MA10",f"{tp_sl['停損一(MA10)']:.2f}", delta="第一停損")
                c3.metric("停損二 MA20",f"{tp_sl['停損二(MA20)']:.2f}", delta="趨勢停損")
                c4.metric("停利一 +8%", f"{tp_sl['停利一(+8%)']:.2f}",  delta="+8%")
                c5.metric("風報比",     str(tp_sl["風報比"]))

                plot_candlestick(yf_code, name, sig_date)

    # ════════════════════════════════════════════════════════════════
    # 分頁三：停損停利總覽
    # ════════════════════════════════════════════════════════════════
    with tab_tpsl:
        st.markdown("### 🎯 所有標的停損停利總覽")
        st.markdown("*建議進場價 = 收盤價 × 1.005（隔日追價空間）*")

        tpsl_cols = [
            "代號","公司名稱","推薦等級","收盤價",
            "建議進場價","停損一(MA10)","停損二(MA20)",
            "停利一(+8%)","停利二(+15%)","風報比",
        ]
        tpsl_cols  = [c for c in tpsl_cols if c in df_result.columns]
        df_tpsl    = df_result[tpsl_cols].reset_index(drop=True)
        df_tpsl.index += 1

        # 風報比 < 1 標紅警示
        def hl_rr(val):
            try:
                return "background-color:#4a1a1a;color:#ff8888;" if float(val) < 1 else ""
            except Exception:
                return ""

        styled_tpsl = df_tpsl.style
        if "風報比" in df_tpsl.columns:
            styled_tpsl = _apply_map(styled_tpsl, hl_rr, ["風報比"])
        fmt_tpsl = {c: "{:.2f}" for c in tpsl_cols if c not in ["代號","公司名稱","推薦等級"]}
        fmt_tpsl = {k: v for k, v in fmt_tpsl.items() if k in df_tpsl.columns}
        styled_tpsl = styled_tpsl.format(fmt_tpsl, na_rep="N/A")

        st.dataframe(styled_tpsl, use_container_width=True,
                     height=min(600, 50+len(df_tpsl)*38))

        st.info("""
💡 **風報比說明**
- 風報比 = (停利一 - 進場價) ÷ (進場價 - 停損一)
- 建議選擇風報比 **≥ 1.5** 的標的，代表潛在獲利是風險的 1.5 倍以上
- 紅色標示 = 風報比 < 1，風險大於報酬，需謹慎評估
        """)

    # ════════════════════════════════════════════════════════════════
    # 分頁四：回測驗證
    # ════════════════════════════════════════════════════════════════
    with tab_backtest:
        st.markdown("### 🔬 歷史回測驗證")
        st.markdown("*對選中的標的執行過去 1 年的歷史回測，驗證策略有效性。*")

        col_bt1, col_bt2 = st.columns([2, 1])
        with col_bt1:
            bt_options = [
                f"{r['代號']} {r.get('公司名稱','')} ({r['推薦指數']}分)"
                for _, r in df_result.head(30).iterrows()
            ]
            bt_selected = st.selectbox("選擇回測標的（前30名）", bt_options)
        with col_bt2:
            hold_days = st.slider("持有天數", 5, 30, 10, 5)

        if st.button("🔬 執行回測", type="primary"):
            bt_code    = bt_selected.split(" ")[0]
            bt_row     = df_result[df_result["代號"] == bt_code].iloc[0]
            bt_yf      = bt_row["YF代號"]
            bt_name    = bt_row.get("公司名稱","")

            with st.spinner(f"正在回測 {bt_code} {bt_name}，請稍候..."):
                bt_result = run_backtest(bt_yf, bt_name, PARAMS, hold_days)

            if bt_result is None:
                st.warning("回測資料不足（需至少 1 年歷史資料）。")
            else:
                st.markdown(f"#### 📊 {bt_code} {bt_name} 回測結果（持有 {hold_days} 日）")

                bm1, bm2, bm3, bm4, bm5 = st.columns(5)
                bm1.metric("訊號次數",    f"{bt_result['訊號次數']} 次")
                bm2.metric("勝率",        f"{bt_result['勝率(%)']} %",
                           delta="優秀" if bt_result['勝率(%)'] >= 60 else "待改善")
                bm3.metric("平均報酬",    f"{bt_result['平均報酬(%)']} %",
                           delta="正期望值" if bt_result['平均報酬(%)'] > 0 else "負期望值")
                bm4.metric("最大獲利",    f"{bt_result['最大獲利(%)']} %")
                bm5.metric("最大虧損",    f"{bt_result['最大虧損(%)']} %")

                # 回測交易明細
                df_trades = bt_result["trades"]
                st.markdown("#### 📋 每筆交易明細")

                def hl_trade(val):
                    if "✅" in str(val): return "background-color:#1a3a1a;color:#66ff66;"
                    if "❌" in str(val): return "background-color:#3a1a1a;color:#ff6666;"
                    return ""

                styled_bt = df_trades.style
                styled_bt = _apply_map(styled_bt, hl_trade, ["結果"])
                styled_bt = styled_bt.format({
                    "進場價"   : "{:.2f}",
                    "出場價"   : "{:.2f}",
                    "報酬率(%)": "{:+.2f}%",
                })
                st.dataframe(styled_bt, use_container_width=True,
                             height=min(400, 50+len(df_trades)*38))

                # 累積報酬曲線
                if PLOTLY_OK and len(df_trades) > 1:
                    st.markdown("#### 📈 累積報酬曲線")
                    df_trades["累積報酬(%)"] = (
                        (1 + df_trades["報酬率(%)"]/100).cumprod() - 1
                    ) * 100
                    fig_bt = go.Figure()
                    fig_bt.add_trace(go.Scatter(
                        x    = df_trades["訊號日期"],
                        y    = df_trades["累積報酬(%)"],
                        mode = "lines+markers",
                        line = dict(color="#e94560", width=2),
                        fill = "tozeroy",
                        fillcolor = "rgba(233,69,96,0.15)",
                        name = "累積報酬",
                    ))
                    fig_bt.add_hline(y=0, line_dash="dash", line_color="#666")
                    fig_bt.update_layout(
                        paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                        font=dict(color="#a8b2d8"),
                        xaxis=dict(gridcolor="#1e2a3a"),
                        yaxis=dict(gridcolor="#1e2a3a", ticksuffix="%"),
                        height=300, margin=dict(l=10,r=10,t=20,b=10),
                    )
                    st.plotly_chart(fig_bt, use_container_width=True)

    # ════════════════════════════════════════════════════════════════
    # 分頁五：加入追蹤清單
    # ════════════════════════════════════════════════════════════════
    with tab_watch_add:
        st.markdown("### 👁️ 加入追蹤清單")
        st.markdown("*將感興趣的標的加入追蹤，下次掃描時可在首頁查看 K 線。*")

        watch_options = [
            f"{r['代號']} {r.get('公司名稱','')} ({r['推薦指數']}分)"
            for _, r in df_result.iterrows()
        ]
        watch_sel  = st.multiselect("選擇要追蹤的標的（可多選）", watch_options)
        watch_note = st.text_input("備註（選填）", placeholder="例：等待回測 MA10 後進場")

        if st.button("➕ 加入追蹤清單", type="primary") and watch_sel:
            for sel in watch_sel:
                code    = sel.split(" ")[0]
                row_sel = df_result[df_result["代號"] == code]
                if not row_sel.empty:
                    yf_t = row_sel.iloc[0]["YF代號"]
                    name = row_sel.iloc[0].get("公司名稱","")
                    add_to_watchlist(yf_t, name, watch_note)
            st.success(f"✅ 已加入 {len(watch_sel)} 個標的到追蹤清單！")

        # 顯示目前追蹤清單
        df_wl_now = get_watchlist()
        if not df_wl_now.empty:
            st.markdown("#### 目前追蹤清單")
            st.dataframe(df_wl_now, use_container_width=True)

    # ── 風險提示 ──────────────────────────────────────────────────────
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    st.warning("""
⚠️ **風險提示**：本系統為純技術面輔助工具，推薦指數不代表必然上漲。
S 級標的仍需搭配基本面與籌碼面確認，並設定明確停損點後再進場。
建議於台股收盤後（13:35 後）執行，確保當日資料完整。
    """)


# ════════════════════════════════════════════════════════════════════════
# 【程式進入點】
# ════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
