import streamlit as st
import time

# ==========================================
# 0. 啟動檢查 (最優先執行)
# ==========================================
st.set_page_config(page_title="專業台股 AI 操盤室", layout="wide", page_icon="📈")

# 如果畫面能顯示這行，代表 Streamlit 活著
# st.toast("系統正在啟動...", icon="🚀") 

# ==========================================
# 1. 安全引入套件 (防止白畫面)
# ==========================================
try:
    import yfinance as yf
    import pandas as pd
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import google.generativeai as genai
    from ta.trend import MACD, SMAIndicator
    from ta.momentum import RSIIndicator, StochasticOscillator
    from ta.volatility import BollingerBands
except ImportError as e:
    st.error(f"⚠️ 環境設置錯誤：{e}")
    st.warning("請確認 requirements.txt 包含: streamlit, yfinance, pandas, plotly, ta, google-generativeai")
    st.stop()

# ==========================================
# 2. 核心邏輯
# ==========================================

@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    """抓取數據並計算指標"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if df.empty:
            return None, None
            
        info = stock.info
        
        # 使用 ta 套件計算
        df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator()
        df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator()
        
        bb = BollingerBands(df['Close'], window=20, window_dev=2)
        df['BB_H'] = bb.bollinger_hband()
        df['BB_L'] = bb.bollinger_lband()
        
        df['RSI'] = RSIIndicator(df['Close'], window=14).rsi()
        
        macd = MACD(df['Close'])
        df['MACD_Bar'] = macd.macd_diff()
        
        kd = StochasticOscillator(df['High'], df['Low'], df['Close'])
        df['K'] = kd.stoch()
        
        return df, info
    except Exception as e:
        st.error(f"數據讀取失敗: {e}")
        return None, None

def get_ai_analysis(api_key, ticker, df):
    if not api_key:
        return "⚠️ 請輸入 API Key 以解鎖 AI 分析"
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        latest = df.iloc[-1]
        prompt = f"""
        分析股票 {ticker}:
        現價: {latest['Close']:.2f}, RSI: {latest['RSI']:.2f}, MACD柱狀: {latest['MACD_Bar']:.2f}
        請給出：1.趨勢判斷 2.關鍵價位 3.操作建議 (條列式, 繁體中文)
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 錯誤: {e}"

# ==========================================
# 3. 介面顯示
# ==========================================
st.title("🚀 專業台股 AI 操盤室")

with st.sidebar:
    st.header("⚙️ 設定")
    ticker_input = st.text_input("股票代號", "2330").upper()
    ticker = f"{ticker_input}.TW" if ticker_input.isdigit() else ticker_input
    
    api_key = st.text_input("Gemini API Key", type="password")
    st.caption("無 Key 僅顯示圖表")

if ticker:
    with st.spinner("正在連線交易所..."):
        df, info = get_stock_data(ticker)

    if df is not None:
        # 顯示數據
        last = df.iloc[-1]
        chg = last['Close'] - df.iloc[-2]['Close']
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("收盤價", f"{last['Close']:.2f}", f"{chg:.2f}")
        c2.metric("成交量", f"{int(last['Volume']/1000)} 張")
        c3.metric("RSI", f"{last['RSI']:.2f}")
        c4.metric("MACD", f"{last['MACD_Bar']:.2f}")

        # 繪圖
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='MA20'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue'), name='MA60'), row=1, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['MACD_Bar'], name='MACD'), row=2, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False, height=500, margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)

        # AI 按鈕
        if st.button("🤖 生成 AI 報告"):
            st.write(get_ai_analysis(api_key, ticker, df))
            
    else:
        st.error("查無資料，請檢查代號")
