import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ta.trend import MACD, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands
import time

# ==========================================
# 1. 頁面配置
# ==========================================
st.set_page_config(page_title="台股即時戰情室", layout="wide", page_icon="⚡")

# CSS 樣式
st.markdown("""
<style>
    .outlook-card {padding: 15px; border-radius: 10px; margin-bottom: 10px; color: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1);}
    .short-term {background: linear-gradient(135deg, #FF512F 0%, #DD2476 100%);}
    .long-term {background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);}
    .big-score {font-size: 24px; font-weight: bold; padding-bottom: 5px;}
    .stButton>button {width: 100%; border-radius: 5px; font-weight: bold;}
    .time-badge {background-color: #333; color: #eee; padding: 2px 8px; border-radius: 4px; font-size: 12px;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 數據核心 (支援多週期)
# ==========================================
def get_stock_data(ticker, interval="1d"):
    """
    interval: '1d' (日K) 或 '60m' (60分K)
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 根據週期抓取不同長度的資料
        if interval == "1d":
            period = "2y" # 日線抓長一點算年線
        else:
            period = "1mo" # 60分K抓1個月就夠了 (Yahoo限制60m最多730天，但資料量太大會慢)
            
        df = stock.history(period=period, interval=interval)
        
        if df.empty: return None, None, None

        # --- A. 均線系統 ---
        # 針對不同週期，均線的意義會不同，但邏輯不變
        df['MA5'] = SMAIndicator(df['Close'], window=5).sma_indicator()
        df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator()
        df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator()
        
        # 只有日線才算年線 (200MA)，分時線算200根意義不大
        if interval == "1d":
            df['MA200'] = SMAIndicator(df['Close'], window=200).sma_indicator()
        else:
            df['MA200'] = np.nan # 分時線不顯示年線

        # --- B. KD 指標 (台股參數 9,3,3) ---
        kd = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=9, smooth_window=3)
        df['K'] = kd.stoch()
        df['D'] = kd.stoch_signal()

        # --- C. MACD 指標 (標準 12,26,9) ---
        macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
        df['DIF'] = macd.macd()
        df['DEM'] = macd.macd_signal()
        df['OSC'] = macd.macd_diff()

        # --- D. RSI 指標 (14) ---
        df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
        
        # --- E. 布林通道 ---
        bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
        df['BB_H'] = bb.bollinger_hband()
        df['BB_L'] = bb.bollinger_lband()

        # --- F. 基本面 (只抓一次) ---
        info = stock.info
        fundamentals = {
            "PE": info.get('trailingPE', None),
            "Vol_Ratio": 0 # 預設
        }
        
        # 計算量能倍數 (今日預估量 / 20日均量)
        # 注意：盤中成交量是累積的，所以早盤看量會不準，這是一個簡單估算
        if len(df) > 20:
            vol_ma = df['Volume'].rolling(20).mean().iloc[-1]
            current_vol = df['Volume'].iloc[-1]
            if vol_ma > 0:
                fundamentals['Vol_Ratio'] = current_vol / vol_ma

        return df, info, fundamentals
    except Exception as e:
        st.error(f"數據計算錯誤: {e}")
        return None, None, None

# ==========================================
# 3. 專家邏輯 (適應雙週期)
# ==========================================
def analyze_logic(df, interval):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 0
    reasons = []

    # 1. KD + MACD 共振 (WinSmart)
    if latest['K'] > latest['D'] and latest['OSC'] > 0:
        if prev['K'] < prev['D'] or prev['OSC'] < 0:
             score += 3
             reasons.append("★ **起漲訊號**：KD金叉且MACD翻紅 (雙指標共振)。")
        else:
             score += 1
             reasons.append("📈 **趨勢續強**：KD與MACD維持多頭。")
    elif latest['K'] < latest['D'] and latest['OSC'] < 0:
        score -= 3
        reasons.append("📉 **空方共振**：KD死叉且MACD綠柱 (雙指標空頭)。")

    # 2. 均線邏輯 (依週期而定)
    if interval == "1d":
        # 日線看生命線 (60MA)
        if latest['Close'] > latest['MA60']:
            score += 1
            reasons.append("🦁 **站上季線**：長線趨勢偏多。")
        else:
            score -= 1
            reasons.append("🐻 **跌破季線**：長線趨勢偏空。")
    else:
        # 60分K看 20MA (相當於日線的 5日線左右概念)
        if latest['Close'] > latest['MA20']:
            score += 1
            reasons.append("⚡ **短線強勢**：股價沿著 20MA (布林中軌) 上攻。")
        else:
            score -= 1
            reasons.append("⚠️ **短線轉弱**：跌破 20MA 支撐。")

    # 3. RSI 過熱
    if latest['RSI'] > 80:
        score -= 1
        reasons.append("🔥 **RSI過熱**：隨時可能回檔。")
    elif latest['RSI'] < 20:
        score += 2
        reasons.append("💎 **RSI超賣**：醞釀反彈。")

    return score, reasons

def get_status_text(score):
    if score >= 3: return "🔥 強力買進"
    elif score >= 1: return "🔴 偏多操作"
    elif score == 0: return "⚪ 觀望整理"
    elif score >= -2: return "🟢 偏空看待"
    else: return "☠️ 賣出/避險"

# ==========================================
# 4. 前端介面
# ==========================================
st.title("⚡ 台股即時戰情室 (盤中實戰版)")

with st.sidebar:
    st.header("⚙️ 戰情設定")
    ticker_input = st.text_input("股票代號", "2330")
    ticker = ticker_input.upper().strip()
    if ticker.isdigit(): ticker += ".TW"
    
    st.markdown("---")
    st.markdown("### 🕒 分析週期")
    # 這裡讓使用者切換模式
    mode = st.radio("選擇模式", ["日 K 線 (收盤分析)", "60 分 K (盤中即時)"], index=0)
    
    interval = "1d" if "日" in mode else "60m"
    
    st.markdown("---")
    # 這是關鍵：強制刷新按鈕
    if st.button("🔄 立即刷新報價"):
        st.cache_data.clear() # 清除快取
        st.rerun() # 重新執行

if ticker:
    # 盤中模式不使用長時間快取，或根本不快取
    if interval == "60m":
        df, info, funds = get_stock_data(ticker, interval) # 不加 spinner 加快體感
        st.caption(f"⚡ 目前模式：**盤中 60分K** (數據延遲約 15 分鐘)")
    else:
        with st.spinner("正在分析日線結構..."):
            df, info, funds = get_stock_data(ticker, interval)
            st.caption("📅 目前模式：**日 K 線** (適合波段分析)")
    
    if df is not None:
        # 1. 報價區
        st.subheader(f"{info.get('longName', ticker)} ({ticker.replace('.TW', '')})")
        last = df.iloc[-1]
        
        # 處理漲跌幅 (Yahoo盤中數據有時候會亂，需做防呆)
        try:
            prev_close = df.iloc[-2]['Close']
            chg = last['Close'] - prev_close
            pct = (chg / prev_close) * 100
        except:
            chg = 0
            pct = 0
            
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("現價", f"{last['Close']:.2f}", f"{chg:.2f} ({pct:.2f}%)")
        col2.metric("週期", f"{interval}", delta="更新中" if interval=='60m' else None, delta_color="off")
        col3.metric("KD(K值)", f"{last['K']:.1f}")
        col4.metric("MACD柱狀", f"{last['OSC']:.2f}")

        # 2. 邏輯分析
        score, reasons = analyze_logic(df, interval)
        
        st.markdown("### 🧭 戰術分析報告")
        # 根據分數變色
        bg_class = "short-term" if score >= 0 else "long-term" # 借用之前的CSS類別，紅多綠空
        if score < 0: bg_class = "long-term" # 綠色
        
        st.markdown(f"""
        <div class="outlook-card {bg_class}">
            <div>綜合評分：<span class="big-score">{score}</span></div>
            <div class="big-score">{get_status_text(score)}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if reasons:
            for r in reasons:
                st.info(r)
        else:
            st.warning("目前無明確技術訊號，建議觀望。")

        # 3. 圖表
        st.markdown("---")
        tab1, tab2 = st.tabs(["📊 主圖 (K線+均線)", "📉 副圖 (KD+MACD)"])
        
        with tab1:
            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='20MA'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=1), name='60MA'))
            # 只有日線顯示年線
            if interval == "1d":
                fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], line=dict(color='purple', width=1), name='200MA'))
            
            fig.update_layout(height=500, xaxis_rangeslider_visible=False, title=f"{ticker} - {interval} 走勢圖")
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            fig2 = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25])
            fig2.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
            
            # KD
            fig2.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='purple'), name='K'), row=2, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='orange', dash='dot'), name='D'), row=2, col=1)
            fig2.add_hline(y=80, line_dash="dot", row=2, col=1, line_color="red")
            fig2.add_hline(y=20, line_dash="dot", row=2, col=1, line_color="green")
            
            # MACD
            colors = ['red' if v > 0 else 'green' for v in df['OSC']]
            fig2.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color=colors, name='MACD'), row=3, col=1)
            
            fig2.update_layout(height=600, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig2, use_container_width=True)

    else:
        st.error("查無資料，請確認股票代號。")
