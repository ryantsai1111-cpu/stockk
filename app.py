import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. 輔助函數：處理股票代號與數據
# ==========================================
def format_ticker(user_input):
    """自動幫忙加上 .TW，除非使用者已經打了 .TWO"""
    user_input = user_input.upper().strip()
    if user_input.endswith('.TW') or user_input.endswith('.TWO'):
        return user_input
    # 預設加上 .TW (上市)
    return f"{user_input}.TW"

def get_fundamentals(ticker):
    """抓取基本面數據：本益比、殖利率、ROE、EPS"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 容錯處理，有些股票可能沒有數據
        data = {
            "name": info.get('longName', ticker),
            "pe_ratio": info.get('trailingPE', 'N/A'),  # 本益比
            "yield": info.get('dividendYield', 0),      # 殖利率
            "roe": info.get('returnOnEquity', 0),       # ROE
            "eps": info.get('trailingEps', 'N/A'),      # EPS
            "market_cap": info.get('marketCap', 'N/A')  # 市值
        }
        
        # 格式化殖利率與 ROE (轉成 %)
        if isinstance(data['yield'], (int, float)):
            data['yield'] = f"{data['yield'] * 100:.2f}%"
        if isinstance(data['roe'], (int, float)):
            data['roe'] = f"{data['roe'] * 100:.2f}%"
            
        return data
    except:
        return None

# ==========================================
# 2. 技術分析運算核心
# ==========================================
def calculate_technical_score(df):
    """
    計算綜合評分 (0-100)，並給出簡單的評語
    """
    # ---------------- 計算指標 ----------------
    # MA (均線)
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    # KD (9,3,3)
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = 100 * (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low'])
    df = df.dropna()
    
    k, d = 50, 50
    k_list, d_list = [], []
    for rsv in df['RSV']:
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k
        k_list.append(k)
        d_list.append(d)
    df['K'] = k_list
    df['D'] = d_list
    
    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = 2 * (df['DIF'] - df['DEA'])
    
    # 布林通道
    df['BB_Up'] = df['MA20'] + 2 * df['Close'].rolling(20).std()
    df['BB_Low'] = df['MA20'] - 2 * df['Close'].rolling(20).std()

    # ---------------- 評分邏輯 ----------------
    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 50 # 基礎分
    reasons = [] # 加分扣分原因
    
    # 1. 均線趨勢 (最重要)
    if last['Close'] > last['MA20'] and last['MA20'] > last['MA60']:
        score += 25
        reasons.append("✅ 股價站上月/季線，多頭排列 (強)")
    elif last['Close'] < last['MA20'] and last['MA20'] < last['MA60']:
        score -= 25
        reasons.append("❌ 股價跌破月/季線，空頭排列 (弱)")
        
    # 2. KD 黃金/死亡交叉
    if last['K'] > last['D']:
        if prev['K'] <= prev['D']: # 剛交叉
            score += 15
            reasons.append("✅ KD 低檔黃金交叉 (買訊)")
        else:
            score += 5 # 維持多頭
    else:
        if prev['K'] >= prev['D']: # 剛死叉
            score -= 15
            reasons.append("❌ KD 高檔死亡交叉 (賣訊)")
        else:
            score -= 5

    # 3. MACD
    if last['MACD_Hist'] > 0:
        score += 10
        if last['MACD_Hist'] > prev['MACD_Hist']:
            reasons.append("✅ MACD 紅柱放大 (動能強)")
    else:
        score -= 10
        
    # 4. 布林通道
    if last['Close'] > last['BB_Up']:
        reasons.append("⚠️ 觸及布林上軌 (短線過熱，小心拉回)")
    elif last['Close'] < last['BB_Low']:
        reasons.append("⚠️ 觸及布林下軌 (超賣，有機會反彈)")

    # 限制分數 0-100
    score = max(0, min(100, score))
    
    # 產生總結
    if score >= 75:
        signal = "積極買進 (Strong Buy)"
        color = "red" # 台股紅是漲
    elif score >= 60:
        signal = "偏多操作 (Buy)"
        color = "red"
    elif score <= 25:
        signal = "快逃 / 做空 (Strong Sell)"
        color = "green" # 台股綠是跌
    elif score <= 40:
        signal = "保守觀望 (Sell/Hold)"
        color = "green"
    else:
        signal = "區間盤整 (Neutral)"
        color = "gray"
        
    return df, score, signal, color, reasons

# ==========================================
# UI 介面設計
# ==========================================
st.set_page_config(page_title="台股速評助手", layout="wide", page_icon="📈")

# 標題區
st.title("📈 台股速評助手")
st.markdown("輸入代號，立刻幫你判斷現在該買還是該賣。")

# 搜尋欄 (置頂，方便手機操作)
col_input, col_btn = st.columns([3, 1])
with col_input:
    ticker_input = st.text_input("輸入股票代號", value="2330", placeholder="例如: 2330, 2603")
with col_btn:
    st.write("") # 排版用
    st.write("") 
    run_btn = st.button("🔍 立即分析", type="primary")

if run_btn:
    ticker = format_ticker(ticker_input)
    
    with st.spinner(f"正在分析 {ticker} 的基本面與籌碼..."):
        try:
            # 1. 抓資料
            df = yf.download(ticker, period="6mo") # 抓半年資料就好，比較快
            fundamentals = get_fundamentals(ticker)
            
            if df.empty:
                st.error(f"❌ 找不到 {ticker} 的資料，請確認代號是否正確。")
                st.stop()
                
            # 處理 MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # 2. 計算
            df, score, signal, color, reasons = calculate_technical_score(df)
            last_price = df.iloc[-1]['Close']
            change = last_price - df.iloc[-2]['Close']
            pct_change = (change / df.iloc[-2]['Close']) * 100
            
            # ================= 顯示結果區 =================
            st.markdown("---")
            
            # --- 區域 A: 大標題結論 (給沒時間的人看) ---
            c1, c2 = st.columns([1, 2])
            
            with c1:
                st.metric("目前股價", f"{last_price:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
            
            with c2:
                # 根據顏色顯示不同風格的警示
                if color == "red":
                    st.success(f"### 🎯 結論：{signal}")
                elif color == "green":
                    st.error(f"### 🎯 結論：{signal}")
                else:
                    st.warning(f"### 🎯 結論：{signal}")
                
                st.progress(score)
                st.caption(f"多空綜合分數：{score} 分 (分數越高越適合買進)")

            # --- 區域 B: 基本面數據 (新增功能) ---
            st.subheader("📊 基本面體質")
            if fundamentals:
                f1, f2, f3, f4 = st.columns(4)
                f1.metric("EPS (每股盈餘)", fundamentals['eps'])
                f2.metric("本益比 (PE)", fundamentals['pe_ratio'])
                f3.metric("殖利率 (Yield)", fundamentals['yield'])
                f4.metric("ROE (股東權益報酬率)", fundamentals['roe'])
            else:
                st.info("查無基本面資料，可能為 ETF 或資料源缺失。")

            # --- 區域 C: 為什麼這樣判斷？ (關鍵原因) ---
            with st.expander("💡 為什麼 AI 給這個建議？點擊查看細節"):
                for reason in reasons:
                    st.write(reason)
            
            # --- 區域 D: K線圖 (視覺化) ---
            st.subheader("📈 走勢圖表")
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.1, row_heights=[0.7, 0.3])

            # K線
            fig.add_trace(go.Candlestick(x=df.index,
                            open=df['Open'], high=df['High'],
                            low=df['Low'], close=df['Close'],
                            name='K線'), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='月線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=1), name='季線'), row=1, col=1)
            
            # KD值
            fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='red', width=1), name='K值'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='green', width=1), name='D值'), row=2, col=1)

            fig.update_layout(height=600, xaxis_rangeslider_visible=False, 
                              title_text=f"{fundamentals['name'] if fundamentals else ticker} - 技術分析圖")
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"發生未預期的錯誤：{e}")
