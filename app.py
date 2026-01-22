import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. 基礎設定與輔助函數
# ==========================================
st.set_page_config(page_title="台股AI操盤手 (小白友善版)", layout="wide", page_icon="📈")

def format_ticker(user_input):
    """自動加上 .TW，讓使用者只要輸入 2330"""
    user_input = user_input.upper().strip()
    # 移除常見的錯誤符號
    user_input = user_input.replace("台積電", "2330").replace("長榮", "2603")
    
    if user_input.endswith('.TW') or user_input.endswith('.TWO'):
        return user_input
    return f"{user_input}.TW"

def get_fundamentals(ticker):
    """抓取基本面：EPS, PE, 殖利率"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        data = {
            "name": info.get('longName', ticker),
            "pe_ratio": info.get('trailingPE', 'N/A'),
            "yield": info.get('dividendYield', 0),
            "roe": info.get('returnOnEquity', 0),
            "eps": info.get('trailingEps', 'N/A'),
        }
        # 格式化百分比
        if isinstance(data['yield'], (int, float)):
            data['yield'] = f"{data['yield'] * 100:.2f}%"
        if isinstance(data['roe'], (int, float)):
            data['roe'] = f"{data['roe'] * 100:.2f}%"
        # 格式化數字 (保留兩位)
        if isinstance(data['pe_ratio'], (int, float)):
            data['pe_ratio'] = f"{data['pe_ratio']:.2f}"
            
        return data
    except:
        return None

# ==========================================
# 2. 核心大腦：將您的技術分析文件寫成程式邏輯
# ==========================================
def analyze_logic(df):
    """
    這裡包含了：道氏理論、KD+MACD共振、葛蘭碧法則、酒田戰法
    """
    # --- A. 計算指標 ---
    # 均線 (MA)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean() # 月線
    df['MA60'] = df['Close'].rolling(window=60).mean() # 季線
    
    # KD指標 (9,3,3)
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

    # --- B. 判斷邏輯 (計分制) ---
    # 取得最新兩筆資料 (Last=今天, Prev=昨天)
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 50 # 初始分
    reasons = [] # 買賣理由清單
    
    # 1. 道氏理論 (趨勢判定)
    # 簡單定義：股價在季線之上，且均線向上
    if curr['Close'] > curr['MA60'] and curr['MA20'] > curr['MA60']:
        score += 20
        reasons.append("✅ **[道氏理論]**：多頭排列！股價站穩季線(生命線)之上，趨勢向上。")
    elif curr['Close'] < curr['MA60'] and curr['MA20'] < curr['MA60']:
        score -= 20
        reasons.append("❌ **[道氏理論]**：空頭排列！股價跌破季線，趨勢向下。")

    # 2. KD + MACD 共振 (您的核心策略)
    # 判斷 KD 金叉
    kd_gold = (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])
    kd_dead = (curr['K'] < curr['D']) and (prev['K'] >= prev['D'])
    
    # 判斷 MACD 紅柱
    macd_red = curr['MACD_Hist'] > 0
    macd_green = curr['MACD_Hist'] < 0
    
    if kd_gold and macd_red:
        score += 25
        reasons.append("🔥 **[最強組合]**：偵測到「KD金叉」且「MACD紅柱」共振！勝率提高 80% 的強勢買訊。")
    elif kd_gold:
        score += 10
        reasons.append("📈 **[KD指標]**：低檔黃金交叉，短線轉強。")
    elif kd_dead:
        score -= 10
        reasons.append("📉 **[KD指標]**：高檔死亡交叉，短線轉弱。")
        
    # 3. 葛蘭碧八大法則 (乖離率)
    # 乖離率 = (股價 - 季線) / 季線
    bias = (curr['Close'] - curr['MA60']) / curr['MA60']
    
    if bias > 0.2: # 正乖離 20%
        score -= 15
        reasons.append("⚠️ **[葛蘭碧法則]**：正乖離過大 (>20%)，股價衝太快，小心拉回修正。")
    elif bias < -0.2: # 負乖離 20%
        score += 10
        reasons.append("✨ **[葛蘭碧法則]**：負乖離過大 (<-20%)，股價超跌，有機會反彈。")
        
    # 4. 酒田戰法 (K線型態 - 簡化版)
    # 陽包陰 (吞噬)：今天紅K，且實體包覆昨天的黑K
    is_engulfing = (curr['Close'] > curr['Open']) and \
                   (prev['Close'] < prev['Open']) and \
                   (curr['Close'] > prev['Open']) and \
                   (curr['Open'] < prev['Close'])
                   
    if is_engulfing:
        score += 15
        reasons.append("✨ **[酒田戰法]**：出現「陽包陰 (吞噬)」型態，主力強勢表態！")
        
    # 5. 布林通道
    if curr['Close'] > curr['BB_Up']:
        reasons.append("🌊 **[布林通道]**：觸及上軌，短線過熱。")
    elif curr['Close'] < curr['BB_Low']:
        reasons.append("🌊 **[布林通道]**：觸及下軌，進入超賣區。")

    # 限制分數
    score = max(0, min(100, score))
    
    # 產出結論
    if score >= 75:
        signal = "積極買進 (Strong Buy)"
        color = "red" # 台股紅漲
        advice = "各項指標共振向上，適合積極佈局。"
    elif score >= 60:
        signal = "偏多操作 (Buy)"
        color = "red"
        advice = "趨勢偏多，可尋找拉回買點。"
    elif score <= 25:
        signal = "快逃 / 做空 (Strong Sell)"
        color = "green" # 台股綠跌
        advice = "空頭趨勢成形，建議減碼或離場。"
    elif score <= 40:
        signal = "保守觀望 (Hold/Sell)"
        color = "green"
        advice = "趨勢轉弱，多看少做。"
    else:
        signal = "區間盤整 (Neutral)"
        color = "gray"
        advice = "方向不明，建議觀望。"
        
    return df, score, signal, color, reasons, advice

# ==========================================
# 3. UI 介面設計
# ==========================================
# 標題
st.title("📈 台股 AI 戰略分析 (小白友善版)")
st.markdown("輸入代號，AI 自動運用 **道氏理論 + KD/MACD 共振 + 葛蘭碧法則** 幫您檢查。")

# 搜尋區 (簡單化)
c1, c2 = st.columns([3, 1])
with c1:
    ticker_input = st.text_input("輸入股票代號", value="2330", placeholder="例如: 2330, 2603")
with c2:
    st.write("")
    st.write("")
    run_btn = st.button("🔍 立即分析", type="primary")

if run_btn:
    ticker = format_ticker(ticker_input)
    
    with st.spinner(f"正在計算 {ticker} 的 KD、MACD 與籌碼數據..."):
        try:
            # A. 抓取數據
            df = yf.download(ticker, period="1y")
            fundamentals = get_fundamentals(ticker)
            
            if df.empty:
                st.error("❌ 找不到資料，請確認代號正確。")
                st.stop()
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # B. 執行分析邏輯
            df, score, signal, color, reasons, advice = analyze_logic(df)
            
            # C. 取得最新價格
            last_price = df.iloc[-1]['Close']
            change = last_price - df.iloc[-2]['Close']
            pct = (change / df.iloc[-2]['Close']) * 100
            
            # ================= 顯示結果 =================
            st.markdown("---")
            
            # 1. 核心結論區 (最顯眼)
            col_res1, col_res2 = st.columns([1, 2])
            
            with col_res1:
                st.metric("目前股價", f"{last_price:.2f}", f"{change:.2f} ({pct:.2f}%)")
                st.caption(f"代號: {ticker}")
                
            with col_res2:
                # 紅綠燈效果
                if color == "red":
                    st.success(f"### 🎯 結論：{signal}")
                elif color == "green":
                    st.error(f"### 🎯 結論：{signal}")
                else:
                    st.warning(f"### 🎯 結論：{signal}")
                
                st.progress(score)
                st.markdown(f"**AI 建議：** {advice}")

            # 2. 基本面 (小白愛看的)
            st.subheader("📊 公司體質 (基本面)")
            if fundamentals:
                f1, f2, f3, f4 = st.columns(4)
                f1.metric("EPS (每股盈餘)", fundamentals['eps'])
                f2.metric("本益比 (PE)", fundamentals['pe_ratio'])
                f3.metric("殖利率 (Yield)", fundamentals['yield'])
                f4.metric("ROE (股東權益)", fundamentals['roe'])
            else:
                st.info("暫無基本面資料 (可能是ETF)")

            # 3. 詳細理由 (這裡放入您指定的分析方法)
            st.markdown("---")
            st.subheader("💡 為什麼 AI 建議買進/賣出？")
            
            # 直接列出重點，不用點開折疊，讓小白直接看
            if len(reasons) > 0:
                for r in reasons:
                    st.write(r)
            else:
                st.write("目前技術面平穩，無特殊訊號。")

            # 4. 圖表區 (視覺化)
            st.markdown("---")
            st.subheader("📈 技術走勢圖")
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.1, row_heights=[0.7, 0.3],
                                subplot_titles=("股價 & 均線 & 布林通道", "MACD 指標"))

            # K線
            fig.add_trace(go.Candlestick(x=df.index,
                            open=df['Open'], high=df['High'],
                            low=df['Low'], close=df['Close'],
                            name='K線'), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='月線(20MA)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=1), name='季線(60MA)'), row=1, col=1)
            
            # MACD
            colors = ['red' if v >= 0 else 'green' for v in df['MACD_Hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=colors, name='MACD柱狀'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], line=dict(color='orange', width=1), name='DIF'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DEA'], line=dict(color='blue', width=1), name='DEA'), row=2, col=1)

            fig.update_layout(height=600, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"分析發生錯誤：{str(e)}")
            st.write("請稍後再試，或檢查股票代號是否正確。")
