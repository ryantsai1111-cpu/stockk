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
st.set_page_config(page_title="台股長短期決策系統", layout="wide", page_icon="📈")

st.markdown("""
<style>
    .outlook-card {
        padding: 20px; 
        border-radius: 10px; 
        margin-bottom: 10px; 
        color: white;
    }
    .short-term {background: linear-gradient(135deg, #FF6B6B 0%, #EE5D5D 100%);}
    .long-term {background: linear-gradient(135deg, #4ECDC4 0%, #45B7AF 100%);}
    .neutral-term {background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%);}
    
    .signal-text {font-size: 16px; margin-bottom: 5px;}
    .big-score {font-size: 32px; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 數據抓取與指標計算
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        # 抓取 2 年數據 (確保有足夠數據計算年線 MA200)
        df = stock.history(period="2y")
        
        if df.empty: return None, None, None

        # --- 技術指標計算 ---
        # 1. 均線 (短中長)
        df['MA5'] = SMAIndicator(df['Close'], window=5).sma_indicator()
        df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator()  # 月線
        df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator()  # 季線 (生命線)
        df['MA200'] = SMAIndicator(df['Close'], window=200).sma_indicator() # 年線 (牛熊分界)
        
        # 2. KD (WinSmart)
        kd = StochasticOscillator(df['High'], df['Low'], df['Close'])
        df['K'] = kd.stoch()
        df['D'] = kd.stoch_signal()
        
        # 3. MACD
        macd = MACD(df['Close'])
        df['DIF'] = macd.macd()
        df['DEM'] = macd.macd_signal()
        df['OSC'] = macd.macd_diff()
        
        # 4. RSI
        df['RSI'] = RSIIndicator(df['Close'], window=14).rsi()
        
        # 5. 布林通道
        bb = BollingerBands(df['Close'], window=20, window_dev=2)
        df['BB_H'] = bb.bollinger_hband()
        df['BB_L'] = bb.bollinger_lband()
        
        # --- 基本面資訊 ---
        info = stock.info
        fundamentals = {
            "PE": info.get('trailingPE', 'N/A'),
            "EPS": info.get('trailingEps', 'N/A'),
            "PB": info.get('priceToBook', 'N/A'),
            "Dividend": info.get('dividendYield', 0),
        }
        
        return df, info, fundamentals
    except Exception as e:
        st.error(f"數據抓取失敗: {e}")
        return None, None, None

# ==========================================
# 3. 核心邏輯：長短期雙軌分析
# ==========================================
def analyze_outlook(df, funds):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # === A. 短期展望 (操作面：1-4週) ===
    # 重點：KD, MACD 柱狀, 乖離率, 量能
    short_score = 0
    short_reasons = []
    
    # 1. WinSmart KD+MACD 策略
    if latest['K'] > latest['D'] and latest['OSC'] > 0:
        short_score += 3
        short_reasons.append("✅ **KD+MACD 共振**：雙指標黃金交叉，短線動能最強。")
    elif latest['K'] < latest['D'] and latest['OSC'] < 0:
        short_score -= 3
        short_reasons.append("❌ **雙指標死叉**：KD與MACD同步向下，短線修正壓力大。")
    
    # 2. 均線乖離 (MA5)
    dist_ma5 = (latest['Close'] - latest['MA5']) / latest['MA5'] * 100
    if dist_ma5 > 5:
        short_score -= 1
        short_reasons.append("⚠️ **短線過熱**：股價正乖離過大 (遠離MA5)，容易拉回。")
    elif latest['Close'] > latest['MA20']:
        short_score += 1
        short_reasons.append("📈 **站上月線**：股價維持在短多結構。")
        
    # 3. 量能突兀
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    if latest['Volume'] > avg_vol * 1.5:
        if latest['Close'] > latest['Open']:
            short_score += 1
            short_reasons.append("🔥 **爆量上攻**：主力資金明顯進駐。")
        else:
            short_score -= 2
            short_reasons.append("💀 **爆量收黑**：高檔有出貨嫌疑。")

    # === B. 長期展望 (投資面：3個月以上) ===
    # 重點：季線, 年線, 本益比, 葛蘭碧法則
    long_score = 0
    long_reasons = []
    
    # 1. 均線多頭排列 (道氏理論)
    if latest['MA20'] > latest['MA60'] > latest['MA200']:
        long_score += 3
        long_reasons.append("🦁 **超級多頭排列**：月線 > 季線 > 年線，長線趨勢極強。")
    
    # 2. 牛熊分界 (年線/季線)
    if latest['Close'] > latest['MA200']:
        long_score += 1
        long_reasons.append("✅ **站穩年線**：股價位於長線牛市區域。")
    else:
        long_score -= 2
        long_reasons.append("🐻 **空頭走勢**：股價低於年線，長線格局偏弱。")
        
    if latest['MA60'] > df.iloc[-20]['MA60']: # 季線翻揚
        long_score += 1
        long_reasons.append("📈 **季線翻揚**：中期趨勢具有支撐力道。")
    
    # 3. 價值評估 (PE)
    pe = funds['PE']
    if pe != 'N/A':
        if pe < 12:
            long_score += 2
            long_reasons.append(f"💎 **價值低估**：本益比 {pe:.1f} 倍處於歷史低檔，適合長線佈局。")
        elif pe > 40:
            long_score -= 1
            long_reasons.append(f"⚠️ **估值過高**：本益比 {pe:.1f} 倍過高，長線獲利空間被壓縮。")

    return {
        "short": {"score": short_score, "reasons": short_reasons},
        "long": {"score": long_score, "reasons": long_reasons}
    }

def get_outlook_color(score):
    if score >= 2: return "🔴 極度看多" # 台股紅是漲
    elif score >= 1: return "🔴 偏多操作"
    elif score == 0: return "⚪ 區間震盪"
    elif score >= -1: return "🟢 偏空看待" # 台股綠是跌
    else: return "🟢 強力賣出/避險"

# ==========================================
# 4. 前端介面
# ==========================================
st.title("🛡️ 全方位台股決策系統 (含長短期展望)")

with st.sidebar:
    st.header("🔍 股票搜尋")
    ticker_input = st.text_input("輸入代號 (如 2330)", "2330")
    ticker = ticker_input.upper().strip()
    if ticker.isdigit(): ticker += ".TW"
    st.info("💡 系統利用「雙軌分析」區分短線價差與長線存股策略。")

if ticker:
    with st.spinner("正在進行長短期交叉運算..."):
        df, info, funds = get_stock_data(ticker)
    
    if df is not None:
        # --- 基本資訊 ---
        st.subheader(f"{info.get('longName', ticker)} ({ticker.replace('.TW', '')})")
        last = df.iloc[-1]
        chg = last['Close'] - df.iloc[-2]['Close']
        pct = (chg / df.iloc[-2]['Close']) * 100
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("現價", f"{last['Close']:.2f}", f"{chg:.2f} ({pct:.2f}%)")
        c2.metric("成交量", f"{int(last['Volume']/1000)} 張")
        c3.metric("本益比 (PE)", f"{funds['PE']}")
        c4.metric("殖利率", f"{funds['Dividend']*100:.2f}%" if funds['Dividend'] else "N/A")

        # --- 長短期展望分析 (New!) ---
        analysis = analyze_outlook(df, funds)
        
        st.markdown("### 🔭 長短期投資展望")
        
        col_short, col_long = st.columns(2)
        
        # 短期卡片
        with col_short:
            status = get_outlook_color(analysis['short']['score'])
            st.markdown(f"""
            <div class="outlook-card short-term">
                <h3>⚡ 短線操作展望 (1-4週)</h3>
                <div class="big-score">{status}</div>
                <p>適合：當沖、隔日沖、波段交易者</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("#### 📝 短線理由：")
            if not analysis['short']['reasons']:
                st.write("目前短線多空力道均衡，無明顯訊號。")
            for r in analysis['short']['reasons']:
                st.write(r)

        # 長期卡片
        with col_long:
            status_long = get_outlook_color(analysis['long']['score'])
            st.markdown(f"""
            <div class="outlook-card long-term">
                <h3>🌳 長線投資展望 (3個月+)</h3>
                <div class="big-score">{status_long}</div>
                <p>適合：存股族、價值投資、趨勢交易者</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("#### 📝 長線理由：")
            if not analysis['long']['reasons']:
                st.write("目前長線趨勢不明朗，建議觀察。")
            for r in analysis['long']['reasons']:
                st.write(r)

        # --- 圖表區 ---
        st.markdown("---")
        tab1, tab2 = st.tabs(["📊 長線趨勢圖 (均線+通道)", "⚡ 短線動能圖 (KD+MACD)"])
        
        with tab1:
            # 長線看 MA60, MA200
            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=2), name='季線 (60MA)'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], line=dict(color='purple', width=2), name='年線 (200MA)'))
            fig.update_layout(height=500, xaxis_rangeslider_visible=False, title="長線趨勢：觀察季線與年線支撐")
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            # 短線看 KD, MACD
            fig2 = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25])
            fig2.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='orange', width=1), name='5日線'), row=1, col=1)
            
            # KD
            fig2.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='purple'), name='K值'), row=2, col=1)
            fig2.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='orange', dash='dot'), name='D值'), row=2, col=1)
            
            # MACD
            colors = ['red' if v > 0 else 'green' for v in df['OSC']]
            fig2.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color=colors, name='MACD柱狀'), row=3, col=1)
            
            fig2.update_layout(height=700, xaxis_rangeslider_visible=False, title="短線動能：觀察 KD 金叉與 MACD 紅柱")
            st.plotly_chart(fig2, use_container_width=True)

    else:
        st.error("查無資料，請確認股票代號。")
