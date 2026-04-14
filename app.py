# ╔══════════════════════════════════════════════════════════════════════╗
# ║  台股全市場選股器 v5.0 — Streamlit 網頁版（v5.0.3）                  ║
# ║  修復：移除 background_gradient（不再依賴 matplotlib）               ║
# ║        改用純 CSS 手動著色，跨環境零依賴                              ║
# ╚══════════════════════════════════════════════════════════════════════╝

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import time
import warnings
from datetime import datetime, timedelta

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

# ════════════════════════════════════════════════════════════════════════
# 【頁面設定】
# ════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title            = "台股選股器 v5.0",
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

    .section-divider { border: none; border-top: 1px solid #2d3561; margin: 1.5rem 0; }

    [data-testid="metric-container"] {
        background: #1a1a2e; border: 1px solid #2d3561;
        border-radius: 8px; padding: 1rem;
    }

    /* 側邊欄：淺色背景確保可讀 */
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
# 【樣式輔助函式】純 CSS 著色，完全不依賴 matplotlib
# ════════════════════════════════════════════════════════════════════════

def _score_to_color(score) -> str:
    """推薦指數 60~100 → 黃橙紅漸層背景色"""
    try:
        v = float(score)
    except (TypeError, ValueError):
        return ""
    t = max(0.0, min(1.0, (v - 60) / 40))   # 0.0（60分）~ 1.0（100分）
    r = int(255)
    g = int(255 * (1 - t * 0.85))
    b = int(50  * (1 - t))
    return f"background-color: rgb({r},{g},{b}); color: #1a1a2e; font-weight: bold;"


def _volratio_to_color(val) -> str:
    """量比 2.5~8 → 白→深紅漸層"""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    t = max(0.0, min(1.0, (v - 2.5) / 5.5))
    r = int(255)
    g = int(220 * (1 - t))
    b = int(220 * (1 - t))
    return f"background-color: rgb({r},{g},{b}); color: #1a1a2e;"


def _chg_to_color(val) -> str:
    """漲幅 -2~+10 → 紅綠漸層"""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v >= 0:
        t = min(1.0, v / 10)
        g = int(180 + 75 * t)
        return f"background-color: rgb(50,{g},50); color: #ffffff;"
    else:
        t = min(1.0, abs(v) / 5)
        r = int(180 + 75 * t)
        return f"background-color: rgb({r},50,50); color: #ffffff;"


def _tangle_to_color(val) -> str:
    """均線糾結度 0~0.05 → 深紫→白（越小越紫）"""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    t = max(0.0, min(1.0, v / 0.05))
    r = int(80  + 175 * t)
    g = int(40  + 215 * t)
    b = int(160 + 95  * t)
    return f"background-color: rgb({r},{g},{b}); color: {'#fff' if t < 0.5 else '#1a1a2e'};"


def style_result_df(df: pd.DataFrame):
    """
    套用純 CSS 樣式到結果 DataFrame。
    完全不使用 background_gradient，零 matplotlib 依賴。
    """

    def highlight_grade(val):
        s = str(val)
        if "S級" in s:
            return "background-color:#7b2d00;color:#ff9944;font-weight:bold"
        elif "A級" in s:
            return "background-color:#1a3a1a;color:#66ff66;font-weight:bold"
        elif "B級" in s:
            return "background-color:#1a1a3a;color:#8888ff"
        return ""

    def highlight_gap(val):
        if "🚀" in str(val):
            return "background-color:#2d1a4a;color:#cc88ff;font-weight:bold"
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
    }
    fmt = {k: v for k, v in fmt.items() if k in df.columns}

    # ── 使用 Styler.apply（逐欄著色，不依賴 matplotlib）────────────
    styled = df.style

    if "推薦指數" in df.columns:
        styled = styled.apply(
            lambda col: [_score_to_color(v) for v in col],
            subset=["推薦指數"]
        )
    if "量比(倍)" in df.columns:
        styled = styled.apply(
            lambda col: [_volratio_to_color(v) for v in col],
            subset=["量比(倍)"]
        )
    if "漲幅(%)" in df.columns:
        styled = styled.apply(
            lambda col: [_chg_to_color(v) for v in col],
            subset=["漲幅(%)"]
        )
    if "均線糾結度" in df.columns:
        styled = styled.apply(
            lambda col: [_tangle_to_color(v) for v in col],
            subset=["均線糾結度"]
        )

    # ── map 相容新舊 Pandas ─────────────────────────────────────────
    pd_ver = tuple(int(x) for x in pd.__version__.split(".")[:2])
    apply_map = styled.map if pd_ver >= (2, 1) else styled.applymap

    if "推薦等級"   in df.columns:
        styled = apply_map(highlight_grade, subset=["推薦等級"])
    if "有跳空缺口" in df.columns:
        styled = apply_map(highlight_gap,   subset=["有跳空缺口"])

    return styled.format(fmt, na_rep="N/A")


def style_score_df(df: pd.DataFrame):
    """套用樣式到加分明細 DataFrame，純 CSS 著色。"""

    def score_color(val, vmin, vmax, r_base, g_base, b_base):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return ""
        t = max(0.0, min(1.0, (v - vmin) / max(vmax - vmin, 1)))
        r = int(r_base * t)
        g = int(g_base * t)
        b = int(b_base * t)
        return (f"background-color: rgb({min(255,r+40)},{min(255,g+40)},{min(255,b+40)});"
                f"color: {'#fff' if t > 0.4 else '#1a1a2e'};")

    fmt = {
        "推薦指數"    : "{} 分",
        "基礎分"      : "{} 分",
        "爆發力加分"  : "+{} 分",
        "籌碼集中加分": "+{} 分",
        "鎖碼強勢加分": "+{} 分",
        "跳空加分"    : "+{} 分",
    }
    fmt    = {k: v for k, v in fmt.items() if k in df.columns}
    styled = df.style

    col_cfg = {
        "推薦指數"    : (60, 100, 255, 160,  0),
        "爆發力加分"  : ( 0,  15, 220,  50, 50),
        "籌碼集中加分": ( 0,  10, 120,  50, 200),
        "鎖碼強勢加分": ( 0,  10,  50, 100, 220),
        "跳空加分"    : ( 0,   5,  50, 180,  80),
    }
    for col, (vmin, vmax, r, g, b) in col_cfg.items():
        if col in df.columns:
            styled = styled.apply(
                lambda c, vmin=vmin, vmax=vmax, r=r, g=g, b=b:
                    [score_color(v, vmin, vmax, r, g, b) for v in c],
                subset=[col]
            )

    return styled.format(fmt, na_rep="N/A")


# ════════════════════════════════════════════════════════════════════════
# 【模組一】股票清單抓取
# ════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def get_all_stocks() -> pd.DataFrame:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }

    df_twse = pd.DataFrame()
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        res.raise_for_status()
        data = res.json()
        df   = pd.DataFrame(data)[["Code", "Name"]]
        df.columns = ["代號", "名稱"]
        df   = df[df["代號"].str.match(r"^\d{4}$")]
        df["YF代號"] = df["代號"] + ".TW"
        df["市場"]   = "上市(TWSE)"
        df_twse = df
    except Exception as e:
        st.warning(f"⚠️ 上市清單主要來源失敗：{e}")
        try:
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                               timeout=15, verify=False)
            res.encoding = "big5"
            tables = pd.read_html(res.text)
            df     = tables[0].copy()
            df.columns = df.iloc[0]
            df     = df.iloc[1:].reset_index(drop=True)
            col    = "有價證券代號及名稱"
            df     = df[[col]].dropna()
            split  = df[col].str.split(r"\s+", n=1, expand=True)
            df["代號"] = split[0]
            df["名稱"] = split[1] if 1 in split.columns else ""
            df     = df[df["代號"].str.match(r"^\d{4}$", na=False)]
            df["YF代號"] = df["代號"] + ".TW"
            df["市場"]   = "上市(TWSE)"
            df_twse = df[["代號", "名稱", "YF代號", "市場"]]
        except Exception as e2:
            st.error(f"❌ 上市清單備用方案失敗：{e2}")

    df_tpex = pd.DataFrame()
    try:
        url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        res.raise_for_status()
        data = res.json()
        df   = pd.DataFrame(data)[["SecuritiesCompanyCode", "CompanyName"]]
        df.columns = ["代號", "名稱"]
        df   = df[df["代號"].str.match(r"^\d{4}$")]
        df["YF代號"] = df["代號"] + ".TWO"
        df["市場"]   = "上櫃(TPEx)"
        df_tpex = df
    except Exception as e:
        st.warning(f"⚠️ 上櫃清單主要來源失敗：{e}")
        try:
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                               timeout=15, verify=False)
            res.encoding = "big5"
            tables = pd.read_html(res.text)
            df     = tables[0].copy()
            df.columns = df.iloc[0]
            df     = df.iloc[1:].reset_index(drop=True)
            col    = "有價證券代號及名稱"
            df     = df[[col]].dropna()
            split  = df[col].str.split(r"\s+", n=1, expand=True)
            df["代號"] = split[0]
            df["名稱"] = split[1] if 1 in split.columns else ""
            df     = df[df["代號"].str.match(r"^\d{4}$", na=False)]
            df["YF代號"] = df["代號"] + ".TWO"
            df["市場"]   = "上櫃(TPEx)"
            df_tpex = df[["代號", "名稱", "YF代號", "市場"]]
        except Exception as e2:
            st.error(f"❌ 上櫃清單備用方案失敗：{e2}")

    frames = [f for f in [df_twse, df_tpex] if not f.empty]
    if not frames:
        st.error("❌ 無法取得任何股票清單，請稍後再試。")
        return pd.DataFrame(columns=["代號", "名稱", "YF代號", "市場"])

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["代號"]).reset_index(drop=True)
    return df_all


# ════════════════════════════════════════════════════════════════════════
# 【模組二】批次下載歷史資料
# ════════════════════════════════════════════════════════════════════════

def download_all_data(
        stock_list   : list,
        lookback_days: int,
        batch_size   : int,
        progress_bar,
        status_text,
) -> dict:
    end_date   = datetime.today()
    start_date = end_date - timedelta(days=int(lookback_days * 1.5))
    end_str    = end_date.strftime("%Y-%m-%d")
    start_str  = start_date.strftime("%Y-%m-%d")

    batches       = [stock_list[i:i+batch_size] for i in range(0, len(stock_list), batch_size)]
    total_batches = len(batches)
    all_data      = {}

    for idx, batch in enumerate(batches):
        pct = (idx + 1) / total_batches
        progress_bar.progress(
            pct,
            text=f"📥 下載中... 第 {idx+1}/{total_batches} 批（已完成 {len(all_data)} 檔）"
        )
        status_text.markdown(f"⏳ 正在下載：`{batch[0]}` ~ `{batch[-1]}`")

        try:
            raw = yf.download(
                tickers     = " ".join(batch),
                start       = start_str,
                end         = end_str,
                group_by    = "ticker",
                auto_adjust = True,
                progress    = False,
                threads     = True,
            )
            if len(batch) == 1:
                ticker = batch[0]
                if not raw.empty:
                    all_data[ticker] = raw.dropna(how="all")
            else:
                for ticker in batch:
                    try:
                        df_s = raw[ticker].dropna(how="all")
                        if not df_s.empty and len(df_s) >= 10:
                            all_data[ticker] = df_s
                    except (KeyError, TypeError):
                        pass
        except Exception:
            pass

        if idx < total_batches - 1:
            time.sleep(1.5)

    return all_data


# ════════════════════════════════════════════════════════════════════════
# 【模組三】評分計算
# ════════════════════════════════════════════════════════════════════════

def calculate_recommendation_score(
        vol_ratio : float,
        tangle_val: float,
        body_pct  : float,
        is_gap_up : bool,
        cfg       : dict
) -> tuple[int, dict]:
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
    total = min(sum(bd.values()), 100)
    return total, bd


def get_grade_label(score: int, cfg: dict) -> str:
    if score >= cfg["grade_s_min"]:
        return "🔥 S級｜強烈推薦"
    elif score >= cfg["grade_a_min"]:
        return "⭐ A級｜推薦"
    else:
        return "👀 B級｜觀察"


# ════════════════════════════════════════════════════════════════════════
# 【模組四】單檔選股邏輯 v5.0
# ════════════════════════════════════════════════════════════════════════

def apply_filter_v5(
        ticker: str,
        df    : pd.DataFrame,
        params: dict,
        cfg   : dict
) -> dict | None:
    p = params
    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in required):
        return None

    df = df[required].copy().dropna(subset=["Close", "Volume"])
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

    cr             = df["High"] - df["Low"]
    df["body_pct"] = (df["Close"] - df["Low"]) / cr.replace(0, float("nan"))

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

    last = df.iloc[-1]
    prev = df.iloc[-2]

    o  = last["Open"];  h  = last["High"]
    l  = last["Low"];   c  = last["Close"]
    v  = last["Volume"]
    avg_vol   = last["avg_vol_5"]
    high_20   = last["high_20"]
    ma5_v     = last["ma5"];   ma10_v  = last["ma10"]
    ma20_v    = last["ma20"];  ma20_pv = prev["ma20"]
    bpct      = last["body_pct"]
    tangle_v  = last["ma_tangle"]
    prev_high = prev["High"];  prev_close = prev["Close"]

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

    return {
        "代號"          : ticker.replace(".TW","").replace(".TWO",""),
        "YF代號"        : ticker,
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
        "訊號日期"      : df.index[-1].strftime("%Y-%m-%d"),
    }


# ════════════════════════════════════════════════════════════════════════
# 【主程式 UI】
# ════════════════════════════════════════════════════════════════════════

def main():

    st.markdown("""
    <div class="main-header">
        <h1>🏆 台股全市場選股器 v5.0</h1>
        <p>終極評分版 — 爆量突破 × 均線多頭 × 推薦指數 × 全市場掃描</p>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════
    # 【側邊欄】
    # ════════════════════════════════════════════════════════════════
    with st.sidebar:
        st.markdown("## ⚙️ 策略參數調整")
        st.markdown("---")

        st.markdown("### 📊 掃描範圍")
        market_choice = st.radio(
            "掃描市場",
            ["🏢 上市 + 上櫃（全市場）", "🏢 僅上市（TWSE）", "🏪 僅上櫃（TPEx）"],
            index=0,
        )
        lite_mode = st.toggle(
            "⚡ 輕量模式（雲端推薦）",
            value=True,
            help="只掃描前 300 檔，避免雲端記憶體不足。"
        )
        lookback_days = st.slider("歷史資料天數",  45,  90,  60,  5)
        batch_size    = st.slider("批次下載大小",  20, 100,  50, 10)

        st.markdown("---")
        st.markdown("### 🛡️ 基礎過濾條件")
        min_price      = st.slider("最低股價（元）",     5,   50,  15,  5)
        liquidity_vol  = st.slider("最低流動性（張）", 100, 2000, 500, 100)
        vol_multiplier = st.slider("爆量倍數",          1.5,  5.0, 2.5, 0.5)
        body_ratio     = st.slider("實體K棒比例",       0.50, 0.95, 0.75, 0.05)
        max_days_stale = st.slider("資料新鮮度（天）",    1,    7,   3,   1)

        st.markdown("---")
        st.markdown("### 🏆 推薦等級門檻")
        grade_s_min = st.slider("S級門檻（強烈推薦）", 70, 95, 85, 5)
        grade_a_min = st.slider("A級門檻（推薦）",     60, 84, 70, 5)

        st.markdown("---")
        scan_button = st.button(
            "🚀 開始全市場掃描",
            type="primary",
            use_container_width=True,
        )
        st.markdown("---")
        st.markdown(
            "<div style='font-size:0.8rem;text-align:center;color:#555;'>"
            "台股選股器 v5.0<br>⚠️ 僅供技術分析參考<br>不構成任何投資建議"
            "</div>",
            unsafe_allow_html=True
        )

    # ════════════════════════════════════════════════════════════════
    # 【說明頁】
    # ════════════════════════════════════════════════════════════════
    if not scan_button:
        col1, col2 = st.columns(2)
        with col1:
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
        with col2:
            st.markdown("### 🏆 推薦指數架構")
            st.markdown("""
| 評分項目 | 最高分 | 觸發條件 |
|---------|--------|---------|
| 基礎分 | 60分 | 通過全部基礎條件 |
| 爆發力 | 15分 | 量比 ≥ 5 倍 |
| 籌碼集中 | 10分 | 三線差距 < 3% |
| 鎖碼強勢 | 10分 | 實體比例 ≥ 95% |
| 跳空表態 | 5分 | 今低 > 昨高 |

| 等級 | 分數 | 建議 |
|------|------|------|
| 🔥 S級 | ≥ 85分 | 強烈推薦 |
| ⭐ A級 | 70~84分 | 推薦 |
| 👀 B級 | 60~69分 | 觀察 |
            """)
        st.info("👈 請在左側調整參數後，點擊『🚀 開始全市場掃描』。")
        st.warning("⏰ 建議台股收盤後（13:35後）執行，確保資料完整。")
        return

    # ════════════════════════════════════════════════════════════════
    # 【整合參數】
    # ════════════════════════════════════════════════════════════════
    PARAMS = {
        "liquidity_vol"  : liquidity_vol * 1000,
        "vol_window"     : 5,
        "vol_multiplier" : vol_multiplier,
        "high_window"    : 20,
        "body_ratio"     : body_ratio,
        "ma_fast"        : 5,
        "ma_slow"        : 10,
        "ma_month"       : 20,
        "min_bars"       : 35,
        "min_price"      : min_price,
        "max_days_stale" : max_days_stale,
    }
    SCORE_CONFIG = {
        "base_score"             : 60,
        "vol_tier_high_min"      : 5.0,
        "vol_tier_high_score"    : 15,
        "vol_tier_mid_min"       : 3.0,
        "vol_tier_mid_score"     : 10,
        "vol_tier_low_min"       : 2.5,
        "vol_tier_low_score"     : 5,
        "tangle_tier_high_max"   : 0.03,
        "tangle_tier_high_score" : 10,
        "tangle_tier_mid_max"    : 0.05,
        "tangle_tier_mid_score"  : 5,
        "body_tier_high_min"     : 0.95,
        "body_tier_high_score"   : 10,
        "body_tier_mid_min"      : 0.85,
        "body_tier_mid_score"    : 5,
        "gap_up_score"           : 5,
        "grade_s_min"            : grade_s_min,
        "grade_a_min"            : grade_a_min,
        "grade_b_min"            : 60,
    }

    # ════════════════════════════════════════════════════════════════
    # 【步驟一】抓取股票清單
    # ════════════════════════════════════════════════════════════════
    with st.status("📋 步驟 1/3：抓取全台股清單...", expanded=True) as status:
        st.write("正在從證交所與櫃買中心取得股票代號清單...")
        df_all_stocks = get_all_stocks()
        if df_all_stocks.empty:
            st.error("❌ 無法取得股票清單，請稍後再試。")
            return

        if "僅上市" in market_choice:
            df_all_stocks = df_all_stocks[df_all_stocks["市場"] == "上市(TWSE)"]
        elif "僅上櫃" in market_choice:
            df_all_stocks = df_all_stocks[df_all_stocks["市場"] == "上櫃(TPEx)"]

        if lite_mode:
            df_all_stocks = df_all_stocks.head(300)
            st.info("⚡ 輕量模式：掃描前 300 檔，約需 3~5 分鐘。")

        total_stocks = len(df_all_stocks)
        st.write(f"✅ 取得 **{total_stocks:,}** 檔股票代號")
        status.update(label=f"✅ 步驟 1/3 完成：取得 {total_stocks:,} 檔", state="complete")

    # ════════════════════════════════════════════════════════════════
    # 【步驟二】批次下載
    # ════════════════════════════════════════════════════════════════
    with st.status("📥 步驟 2/3：批次下載歷史資料...", expanded=True) as status:
        st.write(f"開始下載 {total_stocks:,} 檔股票的歷史 K 線資料...")
        progress_bar = st.progress(0, text="準備下載...")
        status_text  = st.empty()

        all_data = download_all_data(
            stock_list    = df_all_stocks["YF代號"].tolist(),
            lookback_days = lookback_days,
            batch_size    = batch_size,
            progress_bar  = progress_bar,
            status_text   = status_text,
        )
        progress_bar.progress(1.0, text="✅ 下載完成！")
        status_text.empty()
        success_count = len(all_data)
        st.write(f"✅ 成功下載 **{success_count:,}** 檔")
        status.update(label=f"✅ 步驟 2/3 完成：下載 {success_count:,} 檔", state="complete")

    # ════════════════════════════════════════════════════════════════
    # 【步驟三】選股與評分
    # ════════════════════════════════════════════════════════════════
    with st.status("🔍 步驟 3/3：執行選股與評分...", expanded=True) as status:
        st.write("套用 7 道基礎過濾條件並計算推薦指數...")
        market_map    = dict(zip(df_all_stocks["YF代號"], df_all_stocks["市場"]))
        name_map      = dict(zip(df_all_stocks["YF代號"], df_all_stocks["名稱"]))
        results       = []
        ticker_list   = list(all_data.items())
        scan_total    = len(ticker_list)
        scan_progress = st.progress(0, text="選股掃描中...")

        for i, (ticker, df_stock) in enumerate(ticker_list):
            if i % 50 == 0:
                scan_progress.progress(
                    (i + 1) / scan_total,
                    text=f"🔎 掃描中... {i+1}/{scan_total} 檔（已找到 {len(results)} 個）"
                )
            try:
                result = apply_filter_v5(ticker, df_stock.copy(), PARAMS, SCORE_CONFIG)
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
    # 【結果呈現】
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
        ["推薦指數", "量比(倍)"], ascending=[False, False]
    ).reset_index(drop=True)
    df_result.index += 1

    df_s = df_result[df_result["推薦指數"] >= SCORE_CONFIG["grade_s_min"]]
    df_a = df_result[
        (df_result["推薦指數"] >= SCORE_CONFIG["grade_a_min"]) &
        (df_result["推薦指數"] <  SCORE_CONFIG["grade_s_min"])
    ]
    df_b = df_result[df_result["推薦指數"] < SCORE_CONFIG["grade_a_min"]]

    # ── Metric 卡片 ──────────────────────────────────────────────────
    st.markdown(f"### 📊 掃描結果摘要 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📊 掃描總檔數",  f"{success_count:,} 檔")
    m2.metric("✅ 符合條件",    f"{len(df_result)} 檔",
              delta=f"通過率 {len(df_result)/success_count*100:.2f}%")
    m3.metric("🔥 S級強烈推薦", f"{len(df_s)} 檔",  delta=f"≥ {grade_s_min} 分")
    m4.metric("⭐ A級推薦",     f"{len(df_a)} 檔",  delta=f"{grade_a_min}~{grade_s_min-1} 分")
    m5.metric("👀 B級觀察",     f"{len(df_b)} 檔",  delta=f"60~{grade_a_min-1} 分")

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── S 級卡片 + 精簡表 ────────────────────────────────────────────
    st.markdown("## 🔥 核心推薦標的")
    st.markdown(f"*推薦指數 ≥ {grade_s_min} 分的 S 級強烈推薦標的*")

    if df_s.empty:
        st.info(
            f"📭 今日無 S 級標的（≥ {grade_s_min} 分）。"
            f"最高分：**{df_result.iloc[0]['代號']}** "
            f"{df_result.iloc[0]['公司名稱']} — "
            f"**{df_result.iloc[0]['推薦指數']} 分**"
        )
    else:
        cols_per_row = 3
        s_list = df_s.reset_index(drop=True)
        for row_start in range(0, len(s_list), cols_per_row):
            cols = st.columns(cols_per_row)
            for ci in range(cols_per_row):
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
            <span class="name"> {row['公司名稱']}</span><br>
            <small style="color:#aaa">{row['市場']} | {row['訊號日期']}</small>
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

        st.markdown("#### 📋 S 級標的精簡表")
        s_cols    = ["代號","公司名稱","市場","收盤價","漲幅(%)","量比(倍)","推薦指數","推薦等級"]
        s_cols    = [c for c in s_cols if c in df_s.columns]
        df_s_disp = df_s[s_cols].reset_index(drop=True)
        df_s_disp.index += 1
        st.dataframe(
            style_result_df(df_s_disp),
            use_container_width=True,
            height=min(400, 50 + len(df_s_disp) * 38),
        )

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── 完整分頁表格 ─────────────────────────────────────────────────
    st.markdown("## 📊 完整評分詳細表")
    tab_all, tab_s, tab_a, tab_b, tab_score = st.tabs([
        f"🔢 全部（{len(df_result)}）",
        f"🔥 S級（{len(df_s)}）",
        f"⭐ A級（{len(df_a)}）",
        f"👀 B級（{len(df_b)}）",
        "🔬 加分明細",
    ])

    detail_cols = [
        "代號","公司名稱","市場",
        "推薦指數","推薦等級",
        "收盤價","漲幅(%)","量比(倍)",
        "當日量(張)","5日均量(張)",
        "MA5","MA10","MA20",
        "月線斜率(%)","距月線乖離(%)",
        "實體比例","均線糾結度",
        "跳空缺口(%)","有跳空缺口","訊號日期",
    ]
    detail_cols = [c for c in detail_cols if c in df_result.columns]

    def show_tab(df_sub):
        if df_sub.empty:
            st.info("此等級無符合標的。")
            return
        d = df_sub[detail_cols].reset_index(drop=True)
        d.index += 1
        st.dataframe(style_result_df(d), use_container_width=True,
                     height=min(600, 50 + len(d) * 38))

    with tab_all:  show_tab(df_result)
    with tab_s:    show_tab(df_s)
    with tab_a:    show_tab(df_a)
    with tab_b:    show_tab(df_b)
    with tab_score:
        st.markdown("#### 🔬 推薦指數加分明細")
        sc = ["代號","公司名稱","推薦指數","基礎分",
              "爆發力加分","籌碼集中加分","鎖碼強勢加分","跳空加分"]
        sc    = [c for c in sc if c in df_result.columns]
        df_sc = df_result[sc].reset_index(drop=True)
        df_sc.index += 1
        st.dataframe(style_score_df(df_sc), use_container_width=True,
                     height=min(600, 50 + len(df_sc) * 38))

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── 統計圖表 ─────────────────────────────────────────────────────
    st.markdown("## 📈 統計分析")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 推薦等級分佈")
        st.bar_chart(
            pd.DataFrame({"標的數": [len(df_s), len(df_a), len(df_b)]},
                         index=["🔥 S級", "⭐ A級", "👀 B級"]),
            color="#e94560"
        )
    with c2:
        st.markdown("#### 市場分佈")
        mc = df_result["市場"].value_counts().reset_index()
        mc.columns = ["市場", "標的數"]
        st.bar_chart(mc.set_index("市場"), color="#0f3460")

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── CSV 下載 ─────────────────────────────────────────────────────
    st.markdown("## 💾 下載結果")
    today_file = datetime.now().strftime("%Y%m%d_%H%M")
    dl1, dl2   = st.columns(2)
    with dl1:
        st.download_button(
            label="📥 下載完整結果 CSV",
            data=df_result.to_csv(encoding="utf-8-sig", index=True),
            file_name=f"台股選股_v5_{today_file}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with dl2:
        if not df_s.empty:
            st.download_button(
                label="🔥 下載 S 級推薦 CSV",
                data=df_s.to_csv(encoding="utf-8-sig", index=True),
                file_name=f"台股S級推薦_v5_{today_file}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    st.warning("""
⚠️ **風險提示**：本系統為純技術面輔助工具，推薦指數不代表必然上漲。
S 級標的仍需搭配基本面與籌碼面確認，並設定明確停損點後再進場。
建議於台股收盤後（13:35 後）執行，確保當日資料完整。
    """)


if __name__ == "__main__":
    main()
