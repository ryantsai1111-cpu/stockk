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
st.set_page_config(page_title="台股專家決策系統", layout="wide", page_icon="📊")

# CSS 優化視覺
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b;}
    .signal-box {padding: 15px; border-radius: 5px; margin-bottom: 10px;}
    .buy-signal {background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb;}
    .sell-signal {background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;}
    .neutral-signal {background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 核心邏輯：專家規則引擎
# ==========================================

@st.cache_data(ttl=3600)
def get_data_and_analyze(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if df.empty: return None, None

        # --- 技術指標計算 (基於上傳的技術分析文件) ---
        # 1. 趨勢指標 (葛蘭碧 / 道氏理論)
        df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator() # 月線
        df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator() # 季線 (生命線)
        
        # 2. 動能指標 (WinSmart KD+MACD)
        macd = MACD(df['Close'])
        df['DIF'] = macd.macd()
        df['DEM'] = macd.macd_signal()
        df['OSC'] = macd.macd_diff() # 柱狀圖
        
        kd = StochasticOscillator(df['High'], df['Low'], df['Close'])
        df['K'] = kd.stoch()
        df['D'] = kd.stoch_signal()
        
        # 3. 相對強弱 (RSI)
        df['RSI'] = RSIIndicator(df['Close'], window=14).rsi()
        
        # 4. 布林通道 (波動率)
        bb = BollingerBands(df['Close'], window=20, window_dev=2)
        df['BB_High'] = bb.bollinger_hband()
        df['BB_Low'] = bb.bollinger_lband()
        
        return df, stock.info
    except Exception as e:
        st.error(f"數據抓取錯誤: {e}")
        return None, None

def expert_diagnosis(df):
    """
    根據使用者上傳的各種技術分析文件，編寫的「寫死」邏輯。
    """
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = {
        "technical": [], # 技術面
        "chips": [],     # 籌碼面
        "news_impact": [], # 消息面(反應在價格上)
        "score": 0       # 綜合評分 (-5 ~ +5)
    }
    
    # --- 1. 技術面判定 (參考 WinSmart KD+MACD 文件) ---
    # 黃金交叉共振
    kd_gold = latest['K'] > latest['D'] and prev['K'] < prev['D']
    macd_gold = latest['OSC'] > 0 and prev['OSC'] < 0
    
    if latest['K'] > latest['D'] and latest['OSC'] > 0:
        signals['technical'].append("✅ [WinSmart策略] KD 與 MACD 呈現雙多頭排列，勝率較高。")
        signals['score'] += 2
    elif latest['K'] < latest['D'] and latest['OSC'] < 0:
        signals['technical'].append("❌ [WinSmart策略] KD 與 MACD 呈現雙空頭排列，建議觀望。")
        signals['score'] -= 2
        
    if kd_gold:
        signals['technical'].append("🚀 [短線訊號] KD 低檔黃金交叉，短線反彈契機。")
        signals['score'] += 1
        
    # 葛蘭碧法則 (季線生命線)
    if latest['Close'] > latest['MA60']:
        if latest['MA60'] > df.iloc[-5]['MA60']:
            signals['technical'].append("✅ [葛蘭碧法則] 股價站上上揚的季線，長線趨勢偏多。")
            signals['score'] += 1
    else:
        signals['technical'].append("⚠️ [葛蘭碧法則] 股價位於季線之下，長線趨勢偏空。")
        signals['score'] -= 1

    # --- 2. 籌碼面判定 (量能分析) ---
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    if latest['Volume'] > avg_vol * 1.5 and latest['Close'] > latest['Open']:
        signals['chips'].append("🔥 [主力動向] 爆量長紅！成交量大於月均量 1.5 倍，主力明顯進駐。")
        signals['score'] += 1
    elif latest['Volume'] > avg_vol * 1.5 and latest['Close'] < latest['Open']:
        signals['chips'].append("💀 [主力動向] 爆量長黑！高檔出貨跡象，需特別小心。")
        signals['score'] -= 2
    else:
        signals['chips'].append("⚖️ [量能] 成交量溫和，無特殊主力動作。")

    # --- 3. 消息/情緒面判定 (RSI & 乖離) ---
    # 利用價格波動來反推消息面衝擊
    if latest['RSI'] > 75:
        signals['news_impact'].append("🔥 [過熱警訊] RSI > 75，市場情緒過度樂觀，隨時可能因利多出盡回檔。")
        signals['score'] -= 1
    elif latest['RSI'] < 25:
        signals['news_impact'].append("💧 [超賣訊號] RSI < 25，市場恐慌過度，可能出現乖離過大的反彈。")
        signals['score'] += 1
    
    # 布林通道擠壓 (變盤前兆)
    bw = (latest['BB_High'] - latest['BB_Low']) / latest['MA20']
    if bw < 0.10: # 頻寬小於 10%
        signals['news_impact'].append("⚡ [變盤預告] 布林通道極度收縮，重大消息即將引發大行情。")

    return signals

# ==========================================
# 3. 前端介面
# ==========================================
st.title("📈 台股個股決策戰情室 (No-AI版)")

with st.sidebar:
    st.header("🔍 股票搜尋")
    ticker_input = st.text_input("請輸入代號 (如 2330)", "2330")
    # 自動補全 .TW
    ticker = ticker_input.upper().strip()
    if ticker.isdigit(): ticker += ".TW"
    
    st.markdown("---")
    st.info("💡 本系統採用「葛蘭碧八大法則」與「WinSmart KD+MACD」策略邏輯進行自動運算，不依賴外部 AI。")

if ticker:
    with st.spinner(f"正在分析 {ticker} 的主力籌碼與技術型態..."):
        df, info = get_data_and_analyze(ticker)
    
    if df is not None:
        # --- A. 股票基本資訊卡 ---
        st.subheader(f"{info.get('longName', ticker)} ({ticker.replace('.TW', '')})")
        
        last = df.iloc[-1]
        chg = last['Close'] - df.iloc[-2]['Close']
        pct = (chg / df.iloc[-2]['Close']) * 100
        color = "red" if chg > 0 else "green" # 台股紅漲綠跌
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("收盤價", f"{last['Close']:.1f}", f"{chg:.1f} ({pct:.1f}%)")
        col2.metric("成交量", f"{int(last['Volume']/1000)} 張")
        col3.metric("RSI (14)", f"{last['RSI']:.1f}")
        col4.metric("K值 (9)", f"{last['K']:.1f}")

        # --- B. 專家診斷結果 (核心優化部分) ---
        diagnosis = expert_diagnosis(df)
        
        st.markdown("### 🧭 投資決策儀表板")
        
        # 顯示綜合建議
        final_score = diagnosis['score']
        if final_score >= 2:
            st.success(f"🚀 **強力買進訊號 (得分 {final_score})**：多項指標共振，趨勢向上。")
        elif final_score <= -2:
            st.error(f"🛑 **賣出/避險訊號 (得分 {final_score})**：空頭排列或過熱，建議減碼。")
        else:
            st.warning(f"⚖️ **區間盤整/觀望 (得分 {final_score})**：多空力道拉鋸。")

        # 使用 Tabs 分類顯示三大面向
        tab1, tab2, tab3 = st.tabs(["📊 技術面分析", "💰 籌碼面分析", "📰 消息與情緒"])
        
        with tab1:
            st.markdown("**依據 WinSmart 與 葛蘭碧法則分析：**")
            for msg in diagnosis['technical']:
                if "✅" in msg or "🚀" in msg:
                    st.markdown(f"<div class='signal-box buy-signal'>{msg}</div>", unsafe_allow_html=True)
                elif "❌" in msg or "⚠️" in msg:
                    st.markdown(f"<div class='signal-box sell-signal'>{msg}</div>", unsafe_allow_html=True)
                else:
                    st.write(msg)
            
            # 繪製 K 線 + MA + 布林
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='月線(20MA)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue'), name='季線(60MA)'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_High'], line=dict(color='gray', width=0.5, dash='dot'), name='布林上緣'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='gray', width=0.5, dash='dot'), name='布林下緣'), row=1, col=1)
            
            # KD 指標
            fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='purple'), name='K值'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='orange', dash='dot'), name='D值'), row=2, col=1)
            
            fig.update_layout(height=500, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.markdown("**依據成交量與主力動向分析：**")
            for msg in diagnosis['chips']:
                st.write(msg)
            
            # 繪製量能與 MACD
            fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.5, 0.5])
            # 成交量
            colors = ['red' if row['Open'] < row['Close'] else 'green' for i, row in df.iterrows()]
            fig2.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='成交量'), row=1, col=1)
            # MACD
            colors_macd = ['red' if v > 0 else 'green' for v in df['OSC']]
            fig2.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color=colors_macd, name='MACD柱狀'), row=2, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['DIF'], line=dict(color='orange'), name='DIF'), row=2, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['DEM'], line=dict(color='blue'), name='DEM'), row=2, col=1)
            
            fig2.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig2, use_container_width=True)

        with tab3:
            st.markdown("**依據市場情緒與乖離率推算：**")
            for msg in diagnosis['news_impact']:
                 st.write(msg)
            
            st.markdown("---")
            st.markdown("#### 📢 相關消息面標籤")
            # 嘗試顯示產業類別作為基本面補充
            st.info(f"所屬產業：{info.get('sector', '未知')} / {info.get('industry', '未知')}")
            st.write(f"市值：{info.get('marketCap', 0)/100000000:.2f} 億")
            st.write(f"本益比 (PE)：{info.get('trailingPE', 'N/A')}")
            st.write("*註：由於未連接外部新聞 API，消息面分析基於價格波動與指標過熱程度進行反推。*")

    else:
        st.error("找不到股票資料，請檢查代號是否正確。")
