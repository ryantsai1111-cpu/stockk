import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ta.trend import MACD, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands

# ==========================================
# 1. 頁面配置
# ==========================================
st.set_page_config(page_title="台股全方位戰情室", layout="wide", page_icon="🏯")

st.markdown("""
<style>
    .outlook-card {padding: 15px; border-radius: 12px; margin-bottom: 15px; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}
    .short-term {background: linear-gradient(135deg, #FF512F 0%, #DD2476 100%);}
    .long-term {background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);}
    .big-score {font-size: 28px; font-weight: bold; border-bottom: 2px solid rgba(255,255,255,0.3); padding-bottom: 10px; margin-bottom: 10px;}
    .signal-reason {background-color: rgba(255,255,255,0.2); padding: 5px 10px; border-radius: 5px; margin-top: 5px; font-size: 14px;}
    .fundamental-box {background-color: #f8f9fa; border-left: 5px solid #11998e; padding: 10px; margin-top: 10px; border-radius: 5px; color: #333;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 數據核心 (雙軌 + 深度基本面)
# ==========================================
def calculate_indicators(df, is_daily=True):
    if df is None or df.empty: return None
    
    # 技術指標
    df['MA5'] = SMAIndicator(df['Close'], window=5).sma_indicator()
    df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator()
    df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator()
    if is_daily:
        df['MA200'] = SMAIndicator(df['Close'], window=200).sma_indicator()

    # KD (9,3,3)
    kd = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=9, smooth_window=3)
    df['K'] = kd.stoch()
    df['D'] = kd.stoch_signal()

    # MACD (12,26,9)
    macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
    df['DIF'] = macd.macd()
    df['DEM'] = macd.macd_signal()
    df['OSC'] = macd.macd_diff()

    # RSI (14)
    df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
    
    return df

def get_hybrid_data(ticker, use_realtime=False):
    try:
        stock = yf.Ticker(ticker)
        
        # 1. 日線數據
        df_daily = stock.history(period="2y", interval="1d")
        df_daily = calculate_indicators(df_daily, is_daily=True)
        
        # 2. 短線數據
        if use_realtime:
            df_short = stock.history(period="1mo", interval="60m")
            df_short = calculate_indicators(df_short, is_daily=False)
            source_text = "盤中 60分K"
        else:
            df_short = df_daily.copy()
            source_text = "收盤 日K線"

        # 3. 深度基本面 (嘗試抓取更多欄位)
        info = stock.info
        fundamentals = {
            "PE": info.get('trailingPE', None),          # 本益比
            "PB": info.get('priceToBook', None),         # 股價淨值比
            "ROE": info.get('returnOnEquity', None),     # ROE
            "Yield": info.get('dividendYield', None),    # 殖利率
            "Margin": info.get('profitMargins', None),   # 淨利率
            "RevenueGr": info.get('revenueGrowth', None) # 營收成長率
        }
        
        return df_daily, df_short, info, fundamentals, source_text

    except Exception as e:
        st.error(f"數據連線錯誤: {e}")
        return None, None, None, None, None

# ==========================================
# 3. 邏輯分析 (含基本面健檢)
# ==========================================
def analyze_structure(df_daily, df_short, funds):
    # --- A. 短線戰術 ---
    latest_s = df_short.iloc[-1]
    prev_s = df_short.iloc[-2]
    s_score = 0
    s_reasons = []
    
    # KD + MACD
    if latest_s['K'] > latest_s['D'] and latest_s['OSC'] > 0:
        if prev_s['K'] < prev_s['D'] or prev_s['OSC'] < 0:
            s_score += 3
            s_reasons.append("★ **買進訊號**：KD金叉且MACD翻紅。")
        else:
            s_score += 1
            s_reasons.append("📈 **趨勢偏多**：指標維持多頭排列。")
    elif latest_s['K'] < latest_s['D'] and latest_s['OSC'] < 0:
        s_score -= 3
        s_reasons.append("📉 **賣出訊號**：KD死叉且MACD綠柱。")
        
    # 均線乖離
    if latest_s['Close'] > latest_s['MA20']:
        s_score += 1
        s_reasons.append("⚡ **短線強勢**：站穩 20MA。")
    else:
        s_score -= 1
        s_reasons.append("⚠️ **短線轉弱**：跌破 20MA。")

    # --- B. 長線戰略 (基本面大幅增強) ---
    latest_l = df_daily.iloc[-1]
    l_score = 0
    l_reasons = []
    
    # 1. 趨勢面 (葛蘭碧)
    if latest_l['Close'] > latest_l['MA60']:
        l_score += 2
        l_reasons.append("🦁 **技術長多**：股價站穩季線 (生命線)。")
    else:
        l_score -= 2
        l_reasons.append("🐻 **技術長空**：股價落於季線之下。")
        
    # 2. 基本面健檢 (Fundamental Health Check)
    f_score = 0
    f_msgs = []
    
    # ROE (股東權益報酬率)
    if funds['ROE']:
        if funds['ROE'] > 0.15: # ROE > 15%
            f_score += 2
            f_msgs.append(f"💎 **優質企業**：ROE 高達 {funds['ROE']*100:.1f}%，獲利效率極佳。")
        elif funds['ROE'] > 0.10:
            f_score += 1
            f_msgs.append(f"✅ **獲利穩健**：ROE {funds['ROE']*100:.1f}%，表現合格。")
            
    # 殖利率 (Yield)
    if funds['Yield']:
        if funds['Yield'] > 0.04: # > 4%
            f_score += 1
            f_msgs.append(f"💰 **高殖利率**：殖利率 {funds['Yield']*100:.1f}%，具備存股價值。")
            
    # 獲利能力 (Margin)
    if funds['Margin']:
        if funds['Margin'] > 0.20:
            f_msgs.append(f"🔥 **高淨利**：淨利率 {funds['Margin']*100:.1f}%，產品具競爭力。")
        elif funds['Margin'] < 0:
            f_score -= 2
            f_msgs.append(f"⚠️ **公司虧損**：淨利率為負，留意營運風險。")
            
    # 評價面 (PE)
    if funds['PE']:
        if funds['PE'] < 15 and f_score > 0: # 便宜且好公司
            f_score += 1
            f_msgs.append(f"🛒 **價格便宜**：本益比 {funds['PE']:.1f} 倍，物美價廉。")
        elif funds['PE'] > 40:
            f_score -= 1
            f_msgs.append(f"⚠️ **價格昂貴**：本益比 {funds['PE']:.1f} 倍，追高風險大。")

    # 將基本面分數加入長線總分
    l_score += f_score
    l_reasons.extend(f_msgs)

    return {
        "short": {"score": s_score, "reasons": s_reasons},
        "long": {"score": l_score, "reasons": l_reasons}
    }

def get_status_text(score):
    if score >= 3: return "🔥 強力買進"
    elif score >= 1: return "🔴 偏多操作"
    elif score == 0: return "⚪ 觀望整理"
    elif score >= -2: return "🟢 偏空看待"
    else: return "☠️ 強力賣出"

# ==========================================
# 4. 前端介面
# ==========================================
st.title("🛡️ 台股全方位戰情室")

with st.sidebar:
    st.header("⚙️ 模式設定")
    ticker_input = st.text_input("股票代號", "2330")
    ticker = ticker_input.upper().strip()
    if ticker.isdigit(): ticker += ".TW"
    
    st.markdown("---")
    mode_select = st.radio("資料來源", ["收盤分析 (日線)", "盤中即時 (60分K)"], index=0)
    use_realtime = True if "盤中" in mode_select else False
    
    st.markdown("---")
    if st.button("🔄 強制刷新報價"):
        st.cache_data.clear()
        st.rerun()

if ticker:
    with st.spinner("正在進行技術與基本面深度運算..."):
        df_daily, df_short, info, funds, source_text = get_hybrid_data(ticker, use_realtime)

    if df_daily is not None:
        # 1. 報價資訊
        st.subheader(f"{info.get('longName', ticker)} ({ticker.replace('.TW', '')})")
        
        last_price = df_short.iloc[-1]['Close']
        try:
            prev_close = df_daily.iloc[-2]['Close']
            chg = last_price - prev_close
            pct = (chg / prev_close) * 100
        except: chg=0; pct=0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("現價", f"{last_price:.2f}", f"{chg:.2f} ({pct:.2f}%)")
        c2.metric("本益比", f"{funds['PE']}" if funds['PE'] else "-")
        c3.metric("殖利率", f"{funds['Yield']*100:.2f}%" if funds['Yield'] else "-")
        c4.metric("ROE", f"{funds['ROE']*100:.1f}%" if funds['ROE'] else "-")
        c5.metric("KD(K)", f"{df_short.iloc[-1]['K']:.1f}")

        # 2. 決策分析
        analysis = analyze_structure(df_daily, df_short, funds)
        
        st.markdown("### 🧭 長短期決策分析")
        col_s, col_l = st.columns(2)
        
        with col_s:
            score = analysis['short']['score']
            st.markdown(f"""
            <div class="outlook-card short-term">
                <div>⚡ <b>短線戰術 ({'60分K' if use_realtime else '日K'})</b></div>
                <div class="big-score">{get_status_text(score)}</div>
                <div>重點：技術指標、價量關係</div>
            </div>
            """, unsafe_allow_html=True)
            for r in analysis['short']['reasons']:
                st.markdown(f"<div class='signal-reason'>{r}</div>", unsafe_allow_html=True)

        with col_l:
            score = analysis['long']['score']
            st.markdown(f"""
            <div class="outlook-card long-term">
                <div>🌳 <b>長線戰略 (趨勢 + 基本面)</b></div>
                <div class="big-score">{get_status_text(score)}</div>
                <div>重點：季線趨勢、ROE、殖利率</div>
            </div>
            """, unsafe_allow_html=True)
            
            # 將基本面理由特別標註
            for r in analysis['long']['reasons']:
                if "ROE" in r or "殖利率" in r or "本益比" in r or "淨利" in r:
                    st.markdown(f"<div class='fundamental-box'>{r}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='signal-reason'>{r}</div>", unsafe_allow_html=True)

        # 3. 圖表
        st.markdown("---")
        tab1, tab2 = st.tabs(["📉 短線動能 (KD+MACD)", "📊 長線趨勢 (均線)"])
        
        with tab1:
            st.caption(f"數據週期：{source_text}")
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25])
            fig.add_trace(go.Candlestick(x=df_short.index, open=df_short['Open'], high=df_short['High'], low=df_short['Low'], close=df_short['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_short.index, y=df_short['MA20'], line=dict(color='orange', width=1), name='20MA'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_short.index, y=df_short['K'], line=dict(color='purple'), name='K'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_short.index, y=df_short['D'], line=dict(color='orange', dash='dot'), name='D'), row=2, col=1)
            fig.add_hline(y=80, line_dash="dot", row=2, col=1, line_color="red")
            fig.add_hline(y=20, line_dash="dot", row=2, col=1, line_color="green")
            colors = ['red' if v > 0 else 'green' for v in df_short['OSC']]
            fig.add_trace(go.Bar(x=df_short.index, y=df_short['OSC'], marker_color=colors, name='MACD'), row=3, col=1)
            fig.update_layout(height=600, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            fig2 = make_subplots(rows=1, cols=1)
            fig2.add_trace(go.Candlestick(x=df_daily.index, open=df_daily['Open'], high=df_daily['High'], low=df_daily['Low'], close=df_daily['Close'], name='K線'))
            fig2.add_trace(go.Scatter(x=df_daily.index, y=df_daily['MA60'], line=dict(color='blue', width=2), name='季線'), row=1, col=1)
            fig2.add_trace(go.Scatter(x=df_daily.index, y=df_daily['MA200'], line=dict(color='purple', width=2), name='年線'), row=1, col=1)
            fig2.update_layout(height=500, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig2, use_container_width=True)

    else:
        st.error("查無資料，請確認股票代號。")
