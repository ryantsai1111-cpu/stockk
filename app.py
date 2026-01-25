import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ta.trend import MACD, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands

# ==========================================
# 1. 頁面配置
# ==========================================
st.set_page_config(page_title="專業台股操盤助手 (圖表版)", layout="wide", page_icon="📈")

# ==========================================
# 2. 核心函數：數據抓取
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if df.empty:
            return None, None
            
        info = stock.info
        
        # --- 計算指標 ---
        # 1. 均線
        df['MA20'] = SMAIndicator(close=df['Close'], window=20).sma_indicator()
        df['MA60'] = SMAIndicator(close=df['Close'], window=60).sma_indicator()
        
        # 2. 布林通道
        bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
        df['BB_High'] = bb.bollinger_hband()
        df['BB_Low'] = bb.bollinger_lband()
        
        # 3. MACD
        macd = MACD(close=df['Close'])
        df['OSC'] = macd.macd_diff() # 柱狀圖
        
        # 4. RSI
        df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
        
        # 5. KD
        kd = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'])
        df['K'] = kd.stoch()
        
        return df, info
    except Exception as e:
        st.error(f"數據抓取錯誤: {e}")
        return None, None

def format_ticker(user_input):
    user_input = user_input.upper().strip()
    if user_input.isdigit():
        return f"{user_input}.TW"
    return user_input

# ==========================================
# 3. 前端介面
# ==========================================
st.title("🚀 專業台股操盤助手 (無 AI 版)")

with st.sidebar:
    st.header("⚙️ 設定面板")
    user_input = st.text_input("輸入股票代號", value="2330")
    ticker = format_ticker(user_input)
    st.info("💡 目前為純圖表模式，無需 API Key 即可使用。")

if ticker:
    with st.spinner(f"正在分析 {ticker} ..."):
        df, info = get_stock_data(ticker)
    
    if df is not None:
        # 1. 數據卡片
        st.subheader(f"{info.get('longName', ticker)}")
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['Close'] - prev['Close']
        pct = (change / prev['Close']) * 100
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("收盤價", f"{latest['Close']:.2f}", f"{change:.2f} ({pct:.2f}%)")
        c2.metric("成交量", f"{int(latest['Volume']/1000)} 張")
        c3.metric("RSI (14)", f"{latest['RSI']:.2f}")
        c4.metric("MACD 柱狀", f"{latest['OSC']:.2f}")

        # 2. 圖表
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
                            subplot_titles=("K線 & 均線", "成交量 & MACD"))

        # K線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                     low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
        
        # 均線
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='月線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue'), name='季線'), row=1, col=1)
        
        # MACD (下圖)
        fig.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color='purple', name='MACD'), row=2, col=1)
        
        fig.update_layout(xaxis_rangeslider_visible=False, height=600, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # 3. 簡單規則判斷 (用程式寫死，不靠 AI)
        st.markdown("### 🔍 系統自動診斷")
        signals = []
        if latest['Close'] > latest['MA20']:
            signals.append("✅ 股價站上月線，短線偏多。")
        else:
            signals.append("🔻 股價跌破月線，短線整理。")
            
        if latest['RSI'] > 70:
            signals.append("⚠️ RSI 進入超買區 (>70)，留意回檔風險。")
        elif latest['RSI'] < 30:
            signals.append("✅ RSI 進入超賣區 (<30)，醞釀反彈。")
            
        if latest['OSC'] > 0 and df.iloc[-2]['OSC'] < 0:
            signals.append("🚀 MACD 黃金交叉，買進訊號浮現。")
            
        for s in signals:
            st.write(s)
            
    else:
        st.error("查無資料，請確認代號。")
