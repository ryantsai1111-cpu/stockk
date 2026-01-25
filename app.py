import streamlit as st

# ==========================================
# 1. 系統配置與安全引入 (防止白畫面)
# ==========================================
st.set_page_config(page_title="專業台股 AI 操盤手", layout="wide", page_icon="📈")

# 嘗試引入外部套件，如果失敗則顯示錯誤引導，而不是崩潰
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
    st.error(f"⚠️ 系統偵測到套件缺失: {e}")
    st.info("請檢查 GitHub 的 requirements.txt 是否包含: streamlit, yfinance, pandas, plotly, ta, google-generativeai")
    st.stop()

# ==========================================
# 2. 核心數據函數 (含快取加速)
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    """
    抓取股價並使用 TA 套件計算技術指標
    """
    try:
        stock = yf.Ticker(ticker)
        # 抓取 1 年份資料以確保指標運算準確
        df = stock.history(period="1y")
        
        if df.empty:
            return None, None
            
        info = stock.info
        
        # --- 使用 TA 套件計算指標 (比手算更準確) ---
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
        df['OSC'] = macd.macd_diff() # 柱狀圖
        
        # 4. RSI
        df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
        
        # 5. KD (隨機指標)
        kd = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'])
        df['K'] = kd.stoch()
        df['D'] = kd.stoch_signal()
        
        return df, info
    except Exception as e:
        st.error(f"數據抓取發生錯誤: {e}")
        return None, None

def format_ticker(user_input):
    """格式化代碼，自動補上 .TW"""
    user_input = user_input.upper().strip()
    if user_input.isdigit(): 
        return f"{user_input}.TW"
    return user_input

# ==========================================
# 3. AI 分析模組 (Gemini)
# ==========================================
def get_ai_analysis(api_key, ticker, df, info):
    if not api_key:
        return "⚠️ 請在左側側邊欄輸入 Google Gemini API Key 才能啟用 AI 分析。"
    
    try:
        genai.configure(api_key=api_key)
        # 優先嘗試免費且快速的 flash 模型，若失敗可改用 gemini-pro
        model = genai.GenerativeModel('gemini-1.5-flash') 
        
        latest = df.iloc[-1]
        
        # 簡單趨勢判斷輔助 AI
        trend_status = "多頭排列" if latest['MA20'] > latest['MA60'] else "空頭或盤整"
        
        prompt = f"""
        你是一位頂尖的華爾街操盤手與技術分析專家。
        請根據以下台灣股票 {info.get('longName', ticker)} ({ticker}) 的最新技術數據，產出一份專業的短評：

        【關鍵數據】
        1. 收盤價：{latest['Close']:.2f} (月線20MA: {latest['MA20']:.2f})
        2. 成交量：{int(latest['Volume']/1000)} 張
        3. RSI(14)：{latest['RSI']:.2f} (判斷是否過熱或超賣)
        4. KD指標：K={latest['K']:.2f}, D={latest['D']:.2f}
        5. MACD柱狀體：{latest['OSC']:.2f}
        6. 目前趨勢：{trend_status}

        【分析輸出要求】
        - 請用條列式，語氣專業直接，不要廢話。
        - 針對「短線交易」給出具體的操作建議 (例如：觀察哪個支撐位，或是否背離)。
        - 最後給出一個綜合評分 (1-10分，10分為強力買進)。
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 連線失敗 (可能是 API Key 錯誤或模型權限問題): {e}"

# ==========================================
# 4. 前端介面佈局
# ==========================================
st.title("🚀 專業台股 AI 操盤戰情室")

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 參數設定")
    user_input = st.text_input("輸入股票代號", value="2330", help="例如 2330 或 2330.TW")
    ticker = format_ticker(user_input)
    
    st.markdown("---")
    st.subheader("🤖 AI 助手設定")
    api_key = st.text_input("Gemini API Key", type="password", help="輸入 Google AI Studio Key 以解鎖 AI 功能")
    
    st.markdown("---")
    st.subheader("📊 圖表層級")
    show_ma = st.checkbox("顯示均線 (MA)", value=True)
    show_bb = st.checkbox("顯示布林通道", value=True)

# --- 主畫面內容 ---
if ticker:
    # 讀取數據 (顯示 Loading 圈圈)
    with st.spinner(f"正在連線證交所抓取 {ticker} 資料..."):
        df, info = get_stock_data(ticker)
    
    if df is not None:
        # 1. 關鍵指標儀表板 (Dashboard)
        st.subheader(f"📈 {info.get('longName', ticker)} ({ticker}) - 即時概況")
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['Close'] - prev['Close']
        pct_change = (change / prev['Close']) * 100
        
        # 根據漲跌變色 (Streamlit Metric 會自動處理，但我們可以計算好顏色邏輯)
        col1, col2, col3, col4, col5 = st.columns(5)
        
        col1.metric("收盤價", f"{latest['Close']:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
        col2.metric("成交量", f"{int(latest['Volume']/1000)} 張")
        col3.metric("RSI (14)", f"{latest['RSI']:.2f}")
        col4.metric("K 值 (KD)", f"{latest['K']:.2f}")
        col5.metric("MACD 柱狀", f"{latest['OSC']:.2f}")
        
        # 2. 專業互動圖表 (Plotly)
        # 建立雙子圖：上面是股價，下面是副指標
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.03, 
            row_heights=[0.7, 0.3],
            subplot_titles=("股價走勢 & 通道結構", "成交量 & MACD 動能")
        )

        # [上圖] K線
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'], name='K線'
        ), row=1, col=1)
        
        # [上圖] 均線
        if show_ma:
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='月線 (20MA)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=1.5), name='季線 (60MA)'), row=1, col=1)

        # [上圖] 布林通道
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_High'], line=dict(color='gray', width=0.5, dash='dot'), name='布林上緣'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='gray', width=0.5, dash='dot'), name='布林下緣'), row=1, col=1)

        # [下圖] 成交量 (紅綠柱狀)
        vol_colors = ['red' if row['Open'] < row['Close'] else 'green' for i, row in df.iterrows()]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=vol_colors, name='成交量', opacity=0.3), row=2, col=1)
        
        # [下圖] MACD 柱狀圖 (疊加顯示)
        # 為了讓 MACD 在成交量圖中明顯，我們用另一種顏色
        macd_colors = ['red' if v > 0 else 'green' for v in df['OSC']]
        fig.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color=macd_colors, name='MACD 柱狀'), row=2, col=1)

        # 圖表美化
        fig.update_layout(
            xaxis_rangeslider_visible=False, 
            height=600,
            hovermode="x unified",
            margin=dict(l=10, r=10, t=30, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 3. AI 分析區塊
        st.markdown("### 🧠 AI 智能解盤")
        st.caption("請先在左側輸入 Google Gemini API Key，點擊下方按鈕即可生成報告。")
        
        if st.button("✨ 立即生成 AI 投資報告"):
            with st.spinner("AI 分析師正在解讀盤勢，請稍候..."):
                analysis_result = get_ai_analysis(api_key, ticker, df, info)
                st.markdown(analysis_result)
                
    else:
        st.error(f"找不到 {ticker} 的資料，請確認股票代號是否正確。")
