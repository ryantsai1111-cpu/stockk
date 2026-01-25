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
# 1. 頁面配置與樣式
# ==========================================
st.set_page_config(page_title="台股全方位決策系統", layout="wide", page_icon="📈")

st.markdown("""
<style>
    .big-font {font-size:20px !important; font-weight: bold;}
    .reason-box {
        padding: 15px; 
        border-radius: 8px; 
        margin-bottom: 10px; 
        border-left: 5px solid #ccc;
        background-color: #f8f9fa;
    }
    .bullish {border-left-color: #28a745; background-color: #d4edda; color: #155724;}
    .bearish {border-left-color: #dc3545; background-color: #f8d7da; color: #721c24;}
    .neutral {border-left-color: #ffc107; background-color: #fff3cd; color: #856404;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 數據抓取與指標計算
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        # 抓取 1 年數據
        df = stock.history(period="1y")
        
        if df.empty: return None, None, None

        # --- 技術指標計算 ---
        # 1. 均線 (趨勢)
        df['MA5'] = SMAIndicator(df['Close'], window=5).sma_indicator()
        df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator() # 月線
        df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator() # 季線
        
        # 2. KD 指標 (WinSmart 策略核心)
        kd = StochasticOscillator(df['High'], df['Low'], df['Close'])
        df['K'] = kd.stoch()
        df['D'] = kd.stoch_signal()
        
        # 3. MACD (動能)
        macd = MACD(df['Close'])
        df['DIF'] = macd.macd()
        df['DEM'] = macd.macd_signal()
        df['OSC'] = macd.macd_diff()
        
        # 4. RSI (情緒)
        df['RSI'] = RSIIndicator(df['Close'], window=14).rsi()
        
        # 5. 布林通道 (波動)
        bb = BollingerBands(df['Close'], window=20, window_dev=2)
        df['BB_H'] = bb.bollinger_hband()
        df['BB_L'] = bb.bollinger_lband()
        
        # --- 基本面資訊 (嘗試抓取) ---
        info = stock.info
        fundamentals = {
            "PE": info.get('trailingPE', 'N/A'),
            "EPS": info.get('trailingEps', 'N/A'),
            "PB": info.get('priceToBook', 'N/A'),
            "MarketCap": info.get('marketCap', 0),
            "Sector": info.get('sector', '未知產業')
        }
        
        return df, info, fundamentals
    except Exception as e:
        st.error(f"數據抓取失敗: {e}")
        return None, None, None

# ==========================================
# 3. 核心邏輯：決策解釋引擎
# ==========================================
def analyze_logic(df, fundamentals):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    reasons = {
        "bullish": [], # 看多理由
        "bearish": [], # 看空理由
        "neutral": []  # 中性/警示
    }
    
    # -----------------------------------
    # A. 技術面分析 (WinSmart + 葛蘭碧)
    # -----------------------------------
    
    # 1. KD + MACD 共振策略
    kd_gold = latest['K'] > latest['D'] and prev['K'] < prev['D']
    macd_gold = latest['OSC'] > 0 and prev['OSC'] < 0
    
    if kd_gold and latest['OSC'] > 0:
        reasons['bullish'].append("🎯 **WinSmart 策略**：KD 黃金交叉且 MACD 柱狀體翻紅，技術面出現強烈買進共振訊號。")
    elif latest['K'] > latest['D'] and latest['OSC'] > 0:
        reasons['bullish'].append("📈 **趨勢續強**：KD 與 MACD 維持雙多頭排列，股價動能強勁。")
    elif latest['K'] < latest['D'] and latest['OSC'] < 0:
        reasons['bearish'].append("📉 **空方控盤**：KD 與 MACD 呈現雙空頭排列，建議避開。")
        
    # 2. 葛蘭碧八大法則 (均線)
    if latest['Close'] > latest['MA60']:
        reasons['bullish'].append("✅ **長線保護短線**：股價位於季線 (60MA) 之上，長期趨勢偏多。")
    else:
        reasons['bearish'].append("⚠️ **趨勢偏空**：股價位於季線 (60MA) 之下，上方壓力沉重。")
        
    if latest['Close'] > latest['MA20'] and prev['Close'] < prev['MA20']:
        reasons['bullish'].append("🚀 **突破月線**：股價剛站上月線，短期轉強訊號。")

    # -----------------------------------
    # B. 籌碼面分析 (量價關係)
    # -----------------------------------
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    vol_ratio = latest['Volume'] / avg_vol if avg_vol > 0 else 0
    
    if vol_ratio > 1.5 and latest['Close'] > latest['Open']:
        reasons['bullish'].append(f"🔥 **主力進駐**：今日成交量為月均量的 {vol_ratio:.1f} 倍且收紅，顯示有大資金進場點火。")
    elif vol_ratio > 1.5 and latest['Close'] < latest['Open']:
        reasons['bearish'].append(f"💀 **高檔出貨**：爆量長黑 (量增 {vol_ratio:.1f} 倍)，主力可能正在倒貨，需嚴防回檔。")
    elif vol_ratio < 0.6:
        reasons['neutral'].append("💤 **人氣退潮**：成交量萎縮，市場觀望氣氛濃厚。")

    # -----------------------------------
    # C. 基本面與評價 (價值投資)
    # -----------------------------------
    pe = fundamentals['PE']
    if pe != 'N/A':
        if pe < 15:
            reasons['bullish'].append(f"💎 **價值低估**：本益比 ({pe:.1f}) 低於 15 倍，具備長線投資價值。")
        elif pe > 40:
            reasons['neutral'].append(f"⚠️ **估值過高**：本益比 ({pe:.1f}) 偏高，股價可能已反應未來利多，追高風險大。")
    
    # -----------------------------------
    # D. 消息/情緒面 (由波動率推算)
    # -----------------------------------
    if latest['RSI'] > 80:
        reasons['bearish'].append("🔥 **情緒過熱**：RSI 指標 > 80，市場貪婪程度極高，隨時可能獲利回吐。")
    elif latest['RSI'] < 20:
        reasons['bullish'].append("💧 **恐慌超賣**：RSI 指標 < 20，市場過度恐慌，醞釀跌深反彈契機。")

    # 寬度擠壓 (Bollinger Band Squeeze)
    bandwidth = (latest['BB_H'] - latest['BB_L']) / latest['MA20']
    if bandwidth < 0.10:
        reasons['neutral'].append("⚡ **變盤前兆**：布林通道極度壓縮，重大消息即將引發大行情 (注意突破方向)。")

    return reasons

# ==========================================
# 4. 前端介面
# ==========================================
st.title("🛡️ 專業級台股決策戰情室")

with st.sidebar:
    st.header("🔍 股票搜尋")
    ticker_input = st.text_input("輸入代號 (如 2330)", "2330")
    ticker = ticker_input.upper().strip()
    if ticker.isdigit(): ticker += ".TW"
    
    st.markdown("---")
    st.info("本系統整合 WinSmart 技術策略、葛蘭碧法則與籌碼分析，自動生成買賣理由。")

if ticker:
    with st.spinner(f"正在深入分析 {ticker} 的各項數據..."):
        df, info, funds = get_stock_data(ticker)
    
    if df is not None:
        # --- 1. 頂部資訊卡 ---
        st.subheader(f"{info.get('longName', ticker)}")
        last = df.iloc[-1]
        chg = last['Close'] - df.iloc[-2]['Close']
        pct = (chg / df.iloc[-2]['Close']) * 100
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("收盤價", f"{last['Close']:.2f}", f"{chg:.2f} ({pct:.2f}%)")
        c2.metric("成交量", f"{int(last['Volume']/1000)} 張")
        c3.metric("RSI 強弱", f"{last['RSI']:.1f}")
        c4.metric("本益比 (PE)", f"{funds['PE']}")
        c5.metric("EPS (TTM)", f"{funds['EPS']}")

        # --- 2. 決策理由詳解 (重點功能) ---
        analysis = analyze_logic(df, funds)
        
        st.markdown("### 🧭 投資決策分析報告")
        
        # 顯示看多理由
        if analysis['bullish']:
            st.markdown("#### ✅ 買進訊號 / 正面因素")
            for reason in analysis['bullish']:
                st.markdown(f"<div class='reason-box bullish'>{reason}</div>", unsafe_allow_html=True)
        
        # 顯示看空理由
        if analysis['bearish']:
            st.markdown("#### 🛑 賣出訊號 / 風險警示")
            for reason in analysis['bearish']:
                st.markdown(f"<div class='reason-box bearish'>{reason}</div>", unsafe_allow_html=True)
                
        # 顯示中性觀察
        if analysis['neutral']:
            st.markdown("#### ⚖️ 中性觀察 / 潛在變數")
            for reason in analysis['neutral']:
                st.markdown(f"<div class='reason-box neutral'>{reason}</div>", unsafe_allow_html=True)

        if not analysis['bullish'] and not analysis['bearish']:
            st.info("目前盤勢膠著，多空訊號不明顯，建議觀望。")

        # --- 3. 視覺化圖表 ---
        st.markdown("---")
        st.markdown("### 📊 技術面與籌碼面圖表")
        
        tab1, tab2 = st.tabs(["K線與均線策略", "MACD與動能"])
        
        with tab1:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            # K線
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
            # 均線
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='月線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue'), name='季線'), row=1, col=1)
            # 布林
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_H'], line=dict(color='gray', width=0.5, dash='dot'), name='布林上緣'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_L'], line=dict(color='gray', width=0.5, dash='dot'), name='布林下緣'), row=1, col=1)
            # 成交量
            colors = ['red' if row['Open'] < row['Close'] else 'green' for i, row in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='成交量'), row=2, col=1)
            
            fig.update_layout(height=600, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            fig2 = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.4, 0.3, 0.3])
            # Price
            fig2.add_trace(go.Scatter(x=df.index, y=df['Close'], name='收盤價'), row=1, col=1)
            # KD
            fig2.add_trace(go.Scatter(x=df.index, y=df['K'], name='K值', line=dict(color='purple')), row=2, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['D'], name='D值', line=dict(color='orange', dash='dot')), row=2, col=1)
            # MACD
            colors_macd = ['red' if v > 0 else 'green' for v in df['OSC']]
            fig2.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color=colors_macd, name='MACD柱狀'), row=3, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['DIF'], name='DIF'), row=3, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['DEM'], name='DEM'), row=3, col=1)
            
            fig2.update_layout(height=700, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig2, use_container_width=True)

    else:
        st.error("查無資料，請確認股票代號。")
