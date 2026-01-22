import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# ==========================================
# 1. 核心運算引擎 (把技術分析邏輯寫死在程式裡)
# ==========================================
def calculate_indicators(df):
    """
    計算所有技術指標：MA, KD, MACD, Bollinger Bands
    """
    # 1. 移動平均線 (葛蘭碧法則用)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean() # 月線
    df['MA60'] = df['Close'].rolling(window=60).mean() # 季線
    
    # 2. KD 指標 (9,3,3)
    # RSV = (今日收盤 - 最近9天最低) / (最近9天最高 - 最近9天最低) * 100
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = 100 * (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low'])
    df = df.dropna()
    
    # 遞迴計算 K 與 D
    k_list = []
    d_list = []
    k = 50 # 初始值
    d = 50
    for rsv in df['RSV']:
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k
        k_list.append(k)
        d_list.append(d)
    
    df['K'] = k_list
    df['D'] = d_list
    
    # 3. MACD 指標 (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = 2 * (df['DIF'] - df['DEA'])
    
    # 4. 布林通道
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Up'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Low'] = df['BB_Mid'] - 2 * df['BB_Std']
    
    return df

def generate_signal_report(df, ticker, name):
    """
    根據計算結果，生成類似 AI 的分析文字
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    report = []
    score = 50 # 初始分數
    
    # --- 1. 道氏理論與趨勢 ---
    trend = "盤整"
    if last['Close'] > last['MA20'] and last['MA20'] > last['MA60']:
        trend = "多頭排列 (Bullish)"
        score += 20
        trend_msg = "✅ **道氏理論**：股價位於月線與季線之上，且均線發散向上，符合多頭特徵。"
    elif last['Close'] < last['MA20'] and last['MA20'] < last['MA60']:
        trend = "空頭排列 (Bearish)"
        score -= 20
        trend_msg = "❌ **道氏理論**：股價跌破月線與季線，均線下彎，空頭趨勢明顯。"
    else:
        trend_msg = "⚠️ **道氏理論**：股價在均線附近震盪，趨勢不明顯。"

    report.append(trend_msg)
    
    # --- 2. KD + MACD 共振 (您的核心策略) ---
    kd_signal = "中性"
    macd_signal = "中性"
    resonance = False
    
    # KD 判斷
    if last['K'] > last['D'] and prev['K'] <= prev['D']:
        kd_signal = "黃金交叉"
        kd_msg = "📈 **KD指標**：出現黃金交叉 (K值向上突破D值)，短線轉強。"
        score += 10
    elif last['K'] < last['D'] and prev['K'] >= prev['D']:
        kd_signal = "死亡交叉"
        kd_msg = "📉 **KD指標**：出現死亡交叉 (K值向下跌破D值)，短線轉弱。"
        score -= 10
    else:
        kd_msg = f"🔸 **KD指標**：K值({last['K']:.1f}) 與 D值({last['D']:.1f}) 無明顯交叉。"

    # MACD 判斷
    if last['MACD_Hist'] > 0 and prev['MACD_Hist'] <= 0:
        macd_signal = "翻紅 (買訊)"
        macd_msg = "🚀 **MACD指標**：柱狀體由綠翻紅，多頭動能轉強。"
        score += 10
    elif last['MACD_Hist'] > 0 and last['MACD_Hist'] > prev['MACD_Hist']:
        macd_msg = "💪 **MACD指標**：紅柱持續放大，多頭動能延續。"
        score += 5
    elif last['MACD_Hist'] < 0:
        macd_msg = "🐻 **MACD指標**：柱狀體為綠色，空方控盤。"
        score -= 5
    else:
        macd_msg = "🔸 **MACD指標**：震盪整理中。"
        
    # 共振判斷
    if (last['K'] > last['D']) and (last['MACD_Hist'] > 0):
        resonance = True
        score += 20
        res_msg = "🔥 **【關鍵訊號】KD+MACD 共振**：偵測到「KD金叉」且「MACD紅柱」，這是高勝率的強勢買訊！"
    else:
        res_msg = "💤 **共振狀態**：未出現 KD+MACD 雙重共振訊號。"
        
    report.append(kd_msg)
    report.append(macd_msg)
    report.append(res_msg)

    # --- 3. 葛蘭碧法則 (均線) ---
    bias = ((last['Close'] - last['MA60']) / last['MA60']) * 100
    ma_msg = f"📏 **葛蘭碧法則**：目前股價與季線乖離率為 {bias:.2f}%。"
    if bias > 20:
        ma_msg += " (乖離過大，留意拉回風險)"
        score -= 5
    elif bias < -20:
        ma_msg += " (負乖離過大，有機會反彈)"
        score += 5
    report.append(ma_msg)

    # --- 4. 布林通道 ---
    if last['Close'] >= last['BB_Up']:
        bb_msg = "⚡ **布林通道**：股價觸及上軌，強勢但也需注意超買。"
    elif last['Close'] <= last['BB_Low']:
        bb_msg = "💧 **布林通道**：股價觸及下軌，處於超賣區。"
    else:
        bb_msg = "🌊 **布林通道**：股價在通道內正常波動。"
    report.append(bb_msg)

    # 限制分數範圍
    score = max(0, min(100, score))
    
    return {
        "text_report": report,
        "score": score,
        "trend": trend,
        "resonance": resonance,
        "price": last['Close'],
        "change": last['Close'] - prev['Close'],
        "pct_change": (last['Close'] - prev['Close']) / prev['Close'] * 100
    }

# ==========================================
# UI 介面
# ==========================================
st.set_page_config(page_title="台股程式化操盤手 (免Key版)", layout="wide", page_icon="📈")

st.title("📈 台股程式化操盤手 (純運算・免API Key)")
st.caption("使用 Python 直接計算：KD + MACD + 葛蘭碧法則 + 布林通道")
st.markdown("---")

# 側邊欄
with st.sidebar:
    st.header("股票設定")
    ticker_input = st.text_input("股票代號 (台股請加 .TW)", value="2330.TW")
    st.caption("例如：2330.TW (台積電), 2603.TW (長榮), 0050.TW")
    run_btn = st.button("🚀 開始計算分析", type="primary")

if run_btn:
    with st.spinner(f"正在從 Yahoo Finance 下載 {ticker_input} 資料並運算中..."):
        try:
            # 1. 下載資料 (抓一年份)
            df = yf.download(ticker_input, period="1y")
            
            if df.empty:
                st.error("❌ 找不到資料，請確認股票代號是否正確 (例如台積電是 2330.TW)")
                st.stop()
            
            # 處理 MultiIndex (新版 yfinance 可能會有)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # 2. 執行運算
            df = calculate_indicators(df)
            result = generate_signal_report(df, ticker_input, ticker_input)
            
            # 3. 顯示儀表板
            st.subheader("📊 訊號儀表板")
            c1, c2, c3, c4 = st.columns(4)
            
            # 決定顏色
            color = "normal"
            if result['score'] >= 70: color = "normal" # Streamlit metric 自動綠色? 不，要手動
            
            c1.metric("目前股價", f"{result['price']:.2f}", f"{result['change']:.2f} ({result['pct_change']:.2f}%)")
            c2.metric("多空分數", f"{result['score']} / 100", delta_color="normal")
            c3.metric("主要趨勢", result['trend'])
            c4.metric("關鍵共振", "YES 🔥" if result['resonance'] else "NO")
            
            st.markdown("---")

            # 4. 顯示自動生成的分析報告
            st.subheader("📝 程式運算分析報告")
            
            # 組合報告文字
            for line in result['text_report']:
                st.markdown(f"- {line}")

            # 5. 繪製互動式圖表 (K線 + MA + KD/MACD)
            st.markdown("---")
            st.subheader("📈 技術分析圖表")
            
            # 建立子圖 (上圖 K線, 下圖 MACD)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.05, row_heights=[0.7, 0.3],
                                subplot_titles=('K線與均線 (MA20/60)', 'MACD 指標'))

            # K線圖
            fig.add_trace(go.Candlestick(x=df.index,
                            open=df['Open'], high=df['High'],
                            low=df['Low'], close=df['Close'],
                            name='K線'), row=1, col=1)
            
            # 均線
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='月線 (MA20)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=1), name='季線 (MA60)'), row=1, col=1)
            
            # 布林通道
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Up'], line=dict(color='gray', width=1, dash='dot'), name='布林上軌'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='gray', width=1, dash='dot'), name='布林下軌'), row=1, col=1)

            # MACD
            # 顏色設定：紅柱代表多，綠柱代表空
            colors = ['red' if v >= 0 else 'green' for v in df['MACD_Hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=colors, name='MACD柱狀體'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], line=dict(color='orange', width=1), name='DIF'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DEA'], line=dict(color='blue', width=1), name='DEA'), row=2, col=1)

            # 設定版面
            fig.update_layout(height=800, xaxis_rangeslider_visible=False, title_text=f"{ticker_input} 技術分析圖")
            st.plotly_chart(fig, use_container_width=True)
            
            # 顯示原始數據表格 (除錯用)
            with st.expander("查看詳細數據表格"):
                st.dataframe(df.tail(10))

        except Exception as e:
            st.error(f"發生錯誤：{e}")
            st.write("建議檢查股票代號是否正確 (台股代號後方需加上 .TW)")
