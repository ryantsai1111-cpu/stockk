import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import google.generativeai as genai
from ta.trend import MACD, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands

# ==========================================
# 1. 頁面配置
# ==========================================
st.set_page_config(page_title="專業台股 AI 操盤助手", layout="wide", page_icon="📈")

# ==========================================
# 2. 核心函數：數據抓取 (含快取機制)
# ==========================================
@st.cache_data(ttl=3600)  # 設定緩存 1 小時，避免重複請求變慢
def get_stock_data(ticker):
    """抓取股價並計算技術指標"""
    try:
        stock = yf.Ticker(ticker)
        # 抓取 1 年份資料以確保指標計算準確
        df = stock.history(period="1y")
        
        if df.empty:
            return None, None
            
        info = stock.info
        
        # --- 使用 TA 套件計算指標 ---
        # 1. 均線 (MA)
        df['MA20'] = SMAIndicator(close=df['Close'], window=20).sma_indicator()
        df['MA60'] = SMAIndicator(close=df['Close'], window=60).sma_indicator()
        
        # 2. 布林通道 (Bollinger Bands)
        bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
        df['BB_High'] = bb.bollinger_hband()
        df['BB_Low'] = bb.bollinger_lband()
        
        # 3. MACD
        macd = MACD(close=df['Close'])
        df['DIF'] = macd.macd()
        df['DEM'] = macd.macd_signal()
        df['OSC'] = macd.macd_diff()
        
        # 4. RSI
        df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
        
        # 5. KD (隨機指標)
        kd = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'])
        df['K'] = kd.stoch()
        df['D'] = kd.stoch_signal()
        
        return df, info
    except Exception as e:
        st.error(f"數據抓取錯誤: {e}")
        return None, None

def format_ticker(user_input):
    """自動格式化股票代碼"""
    user_input = user_input.upper().strip()
    if user_input.isdigit(): # 如果只輸入數字 (如 2330)
        return f"{user_input}.TW"
    return user_input

# ==========================================
# 3. AI 分析模組
# ==========================================
def get_ai_analysis(api_key, ticker, df, info):
    if not api_key:
        return "⚠️ 請在左側側邊欄輸入 Google Gemini API Key 以啟用 AI 分析功能。"
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') # 使用較快且免費的模型
        
        latest = df.iloc[-1]
        trend = "多頭排列" if latest['MA20'] > latest['MA60'] else "空頭/盤整"
        
        prompt = f"""
        你是一位專業的股市分析師。請根據以下台灣股票 {info.get('longName', ticker)} ({ticker}) 的數據撰寫一份簡短的技術分析報告：
        
        【當前數據】
        - 收盤價：{latest['Close']:.2f}
        - 漲跌：{latest['Close'] - df.iloc[-2]['Close']:.2f}
        - 成交量：{latest['Volume']}
        - RSI(14)：{latest['RSI']:.2f} (判斷是否超買/超賣)
        - MACD柱狀圖：{latest['OSC']:.2f}
        - KD值：K={latest['K']:.2f}, D={latest['D']:.2f}
        - 均線狀態：{trend} (月線 {latest['MA20']:.2f}, 季線 {latest['MA60']:.2f})
        
        【分析要求】
        1. 判斷目前趨勢（多頭、空頭或盤整）。
        2. 給出關鍵支撐或壓力位的觀察建議。
        3. 針對短線操作者給出 3 點具體操作建議。
        4. 語氣專業、客觀，並使用繁體中文。
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 分析失敗: {e}"

# ==========================================
# 4. 前端介面邏輯
# ==========================================
st.title("🚀 專業台股 AI 操盤助手")

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 設定面板")
    user_input = st.text_input("輸入股票代號", value="2330", help="例如 2330 或 2330.TW")
    ticker = format_ticker(user_input)
    
    st.markdown("---")
    st.markdown("### 🤖 AI 設定")
    api_key = st.text_input("Gemini API Key", type="password", help="請輸入 Google AI Studio 的 API Key")
    
    st.markdown("---")
    st.markdown("### 📊 圖表指標")
    show_ma = st.checkbox("顯示均線 (MA)", value=True)
    show_bb = st.checkbox("顯示布林通道", value=True)

# --- 主程式 ---
if ticker:
    with st.spinner(f"正在分析 {ticker} ..."):
        df, info = get_stock_data(ticker)
    
    if df is not None:
        # 1. 頂部儀表板 (Metrics)
        st.subheader(f"{info.get('longName', ticker)} ({ticker})")
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['Close'] - prev['Close']
        pct_change = (change / prev['Close']) * 100
        color = "normal"
        if change > 0: color = "normal" # Streamlit metric 自動會綠色
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("收盤價", f"{latest['Close']:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
        col2.metric("成交量", f"{int(latest['Volume']/1000)} 張")
        col3.metric("RSI 強弱", f"{latest['RSI']:.2f}")
        col4.metric("K 值 (KD)", f"{latest['K']:.2f}")
        col5.metric("MACD 柱狀", f"{latest['OSC']:.2f}")
        
        # 2. 互動式圖表 (Plotly)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.03, row_heights=[0.7, 0.3],
                            subplot_titles=("股價走勢 & 通道", "成交量 & MACD"))

        # 上圖：K線
        fig.add_trace(go.Candlestick(x=df.index,
                                     open=df['Open'], high=df['High'],
                                     low=df['Low'], close=df['Close'],
                                     name='K線'), row=1, col=1)
        
        # 上圖：均線
        if show_ma:
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='月線(20MA)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=1.5), name='季線(60MA)'), row=1, col=1)
            
        # 上圖：布林通道
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_High'], line=dict(color='gray', width=0.5, dash='dot'), name='布林上緣'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='gray', width=0.5, dash='dot'), name='布林下緣'), row=1, col=1)

        # 下圖：成交量 (Bar)
        colors = ['red' if row['Open'] < row['Close'] else 'green' for i, row in df.iterrows()]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='成交量', opacity=0.5), row=2, col=1)
        
        # 下圖：MACD (疊加在成交量上，使用副座標軸會更複雜，這裡先簡單共用Y軸或僅展示趨勢)
        # 為了清晰，這裡我們將 MACD 獨立顯示或標準化，簡單起見，我們將 MACD 柱狀圖縮放後顯示，或者只顯示成交量
        # 這裡選擇：顯示 MACD 柱狀圖 (因為它是判斷背離的關鍵)
        fig.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color='blue', name='MACD柱狀'), row=2, col=1)

        # 設定圖表樣式
        fig.update_layout(xaxis_rangeslider_visible=False, height=600, 
                          margin=dict(l=20, r=20, t=40, b=20),
                          hovermode="x unified")
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 3. AI 分析報告區塊
        st.markdown("### 🤖 AI 智能解盤")
        if st.button("生成 AI 分析報告"):
            with st.spinner("AI 正在思考中，請稍候..."):
                analysis = get_ai_analysis(api_key, ticker, df, info)
                st.markdown(analysis)
            
    else:
        st.error("查無資料，請確認股票代號是否正確 (例如 2330)。")
