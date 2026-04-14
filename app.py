import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests

# 網頁基本設定
st.set_page_config(page_title="台股終極選股器 v5.0", page_icon="🏆", layout="wide")

st.title("🏆 台股全市場選股器 v5.0 — 終極評分版")
st.markdown("結合爆量突破、月線保護與多因子評分模型的專屬量化工具。")

# ════════════════════════════════════════════════════════════════
# 【側邊欄：參數設定】
# ════════════════════════════════════════════════════════════════
st.sidebar.header("⚙️ 策略參數調整")

min_price = st.sidebar.slider("🛡️ 最低股價門檻", 5, 100, 15)
vol_multiplier = st.sidebar.slider("💥 爆量倍數", 1.5, 5.0, 2.5, 0.1)
body_ratio = st.sidebar.slider("📈 實體紅K比例", 0.5, 1.0, 0.75, 0.05)
max_days_stale = st.sidebar.slider("📅 資料新鮮度 (天)", 1, 7, 3)

# 評分常數 (隱藏在背景，不讓側邊欄太雜亂)
SCORE_CONFIG = {
    "base_score": 60,
    "vol_tier_high_min": 5.0, "vol_tier_high_score": 15,
    "vol_tier_mid_min": 3.0, "vol_tier_mid_score": 10,
    "vol_tier_low_min": 2.5, "vol_tier_low_score": 5,
    "tangle_tier_high_max": 0.03, "tangle_tier_high_score": 10,
    "tangle_tier_mid_max": 0.05, "tangle_tier_mid_score": 5,
    "body_tier_high_min": 0.95, "body_tier_high_score": 10,
    "body_tier_mid_min": 0.85, "body_tier_mid_score": 5,
    "gap_up_score": 5,
    "grade_s_min": 85, "grade_a_min": 70, "grade_b_min": 60,
}

PARAMS = {
    "liquidity_vol": 500_000, "vol_window": 5, "vol_multiplier": vol_multiplier,
    "high_window": 20, "body_ratio": body_ratio, "ma_fast": 5, "ma_slow": 10,
    "ma_month": 20, "min_bars": 35, "min_price": min_price, "max_days_stale": max_days_stale,
}

# ════════════════════════════════════════════════════════════════
# 【核心邏輯區】(包含快取機制以加速網頁載入)
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600) # 快取 1 小時，避免重複下載
def get_stock_list():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    res = requests.get(url)
    df = pd.read_html(res.text)[0]
    df.columns = df.iloc[0]
    df = df.iloc[1:]
    df = df.dropna(subset=['有價證券代號及名稱'])
    df['代號'] = df['有價證券代號及名稱'].str.split('　').str[0]
    df['名稱'] = df['有價證券代號及名稱'].str.split('　').str[1]
    df = df[df['代號'].str.len() == 4]
    df['YF代號'] = df['代號'] + '.TW'
    df['市場'] = '上市'
    return df[['代號', '名稱', 'YF代號', '市場']]

# 這裡省略了完整的 apply_momentum_filter_v5 函式內容
# 請將上一篇對話中的 calculate_recommendation_score, get_grade, apply_momentum_filter_v5 完整貼在這裡
# ... (為了版面簡潔，請將 v5.0 的三個函式貼入此處) ...

# ════════════════════════════════════════════════════════════════
# 【網頁互動區】
# ════════════════════════════════════════════════════════════════

if st.button("🚀 開始全市場掃描", type="primary"):
    
    st.info("正在取得台股清單...")
    df_stocks = get_stock_list()
    # 為了避免免費網頁伺服器超時，網頁版建議先掃描前 300 檔大型股或隨機抽樣
    # 若要全掃，需等待約 1-2 分鐘
    tickers = df_stocks['YF代號'].tolist()[:300] # 範例：先掃描 300 檔
    name_map = dict(zip(df_stocks["YF代號"], df_stocks["名稱"]))
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results = []
    
    # 批次下載與運算
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    for i, ticker in enumerate(tickers):
        status_text.text(f"掃描進度：{i+1} / {len(tickers)} ({ticker})")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            df_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if not df_data.empty:
                # 呼叫您的 v5.0 核心函式
                # result = apply_momentum_filter_v5(ticker, df_data, PARAMS, SCORE_CONFIG)
                # if result:
                #     result["公司名稱"] = name_map.get(ticker, "")
                #     results.append(result)
                pass # 這裡替換成實際呼叫
        except:
            continue
            
    status_text.text("✅ 掃描完成！")
    
    if results:
        df_result = pd.DataFrame(results)
        df_result = df_result.sort_values("推薦指數", ascending=False).reset_index(drop=True)
        
        st.subheader("🔥 核心推薦標的 (S級)")
        df_s = df_result[df_result["推薦指數"] >= 85]
        if not df_s.empty:
            st.dataframe(df_s, use_container_width=True)
        else:
            st.warning("今日無 S 級標的。")
            
        st.subheader("📊 完整評分詳細表")
        st.dataframe(df_result, use_container_width=True)
    else:
        st.error("📭 今日無標的符合條件，請嘗試在左側放寬參數。")
