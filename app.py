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
st.set_page_config(page_title="台股專家決策系統 (驗證版)", layout="wide", page_icon="⚖️")

# CSS 樣式：讓訊號卡片更清晰
st.markdown("""
<style>
    .outlook-card {padding: 20px; border-radius: 12px; margin-bottom: 15px; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}
    .short-term {background: linear-gradient(135deg, #FF512F 0%, #DD2476 100%);} /* 紅色系：短線 */
    .long-term {background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);} /* 綠色系：長線 */
    .signal-reason {background-color: rgba(255,255,255,0.15); padding: 8px; border-radius: 5px; margin-top: 5px; font-size: 14px;}
    .big-score {font-size: 28px; font-weight: bold; border-bottom: 2px solid rgba(255,255,255,0.3); padding-bottom: 10px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 數據核心 (參數嚴格對照文件)
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y") # 抓兩年以計算年線
        
        if df.empty: return None, None, None

        # --- A. 均線系統 (葛蘭碧法則 / 道氏理論) ---
        # 5日線 (短線攻擊)
        df['MA5'] = SMAIndicator(df['Close'], window=5).sma_indicator()
        # 20日線 (月線/支撐)
        df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator()
        # 60日線 (季線/生命線 - 葛蘭碧核心)
        df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator()
        # 200日線 (年線/牛熊分界)
        df['MA200'] = SMAIndicator(df['Close'], window=200).sma_indicator()

        # --- B. KD 指標 (WinSmart 策略) ---
        # 修正：台股慣用參數為 (9, 3, 3)，非預設的 14
        kd = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], 
                                  window=9, smooth_window=3)
        df['K'] = kd.stoch()
        df['D'] = kd.stoch_signal()

        # --- C. MACD 指標 (動能) ---
        # 標準參數 (12, 26, 9)
        macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
        df['DIF'] = macd.macd()
        df['DEM'] = macd.macd_signal()
        df['OSC'] = macd.macd_diff() # 柱狀圖

        # --- D. RSI 指標 (情緒) ---
        # 參數 (14)
        df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
        
        # --- E. 布林通道 (波動率) ---
        bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
        df['BB_H'] = bb.bollinger_hband()
        df['BB_L'] = bb.bollinger_lband()
        df['BB_W'] = (df['BB_H'] - df['BB_L']) / df['MA20'] # 通道寬度 (擠壓判斷)

        # --- F. 基本面概況 ---
        info = stock.info
        fundamentals = {
            "PE": info.get('trailingPE', None), # 本益比
            "Dividend": info.get('dividendYield', None), # 殖利率
            "PB": info.get('priceToBook', None), # 股價淨值比
        }

        return df, info, fundamentals
    except Exception as e:
        st.error(f"數據計算錯誤: {e}")
        return None, None, None

# ==========================================
# 3. 專家邏輯引擎 (依據上傳文件編寫)
# ==========================================
def analyze_logic(df, funds):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # === 短線戰術分析 (Short-term Tactics) ===
    # 依據：WinSmart KD+MACD, 量價關係
    short_score = 0
    short_reasons = []

    # 1. WinSmart 雙指標共振 (權重高)
    # 邏輯：KD金叉 (K>D) 且 MACD 柱狀圖為正 (OSC>0)
    if latest['K'] > latest['D'] and latest['OSC'] > 0:
        # 進階確認：是否剛轉強 (昨天K<D 或 昨天綠柱)
        if prev['K'] < prev['D'] or prev['OSC'] < 0:
             short_score += 3
             short_reasons.append("★ **WinSmart 起漲點**：KD 金叉且 MACD 翻紅，雙指標共振確認！")
        else:
             short_score += 1
             short_reasons.append("📈 **多頭續攻**：KD 與 MACD 維持多頭排列，動能強勁。")
    elif latest['K'] < latest['D'] and latest['OSC'] < 0:
        short_score -= 3
        short_reasons.append("📉 **雙指標死叉**：KD 與 MACD 同步向下，短線空方主導。")

    # 2. 成交量異常 (籌碼面)
    vol_ma = df['Volume'].rolling(20).mean().iloc[-1]
    if latest['Volume'] > vol_ma * 1.5:
        if latest['Close'] > latest['Open']:
            short_score += 1
            short_reasons.append("🔥 **爆量長紅**：成交量放大 1.5 倍，主力資金進駐。")
        else:
            short_score -= 2
            short_reasons.append("💀 **爆量收黑**：高檔爆大量收黑 K，疑似主力出貨。")

    # 3. RSI 極端值 (乖離率概念)
    if latest['RSI'] > 80:
        short_score -= 1
        short_reasons.append("⚠️ **過熱警訊**：RSI > 80，短線隨時可能回檔整理。")
    elif latest['RSI'] < 20:
        short_score += 2
        short_reasons.append("💎 **超賣反彈**：RSI < 20，乖離過大，醞釀反彈契機。")

    # === 長線戰略分析 (Long-term Strategy) ===
    # 依據：葛蘭碧八大法則, 道氏理論, 基本面
    long_score = 0
    long_reasons = []

    # 1. 葛蘭碧法則 (生命線 MA60)
    if latest['Close'] > latest['MA60']:
        if latest['MA60'] > df.iloc[-20]['MA60']: # 季線翻揚
            long_score += 2
            long_reasons.append("🦁 **葛蘭碧多頭**：股價站穩季線且季線翻揚向上，長多格局確立。")
        else:
            long_score += 1
            long_reasons.append("✅ **站上季線**：股價位於生命線之上，中長線偏多。")
    else:
        long_score -= 2
        long_reasons.append("🐻 **葛蘭碧空頭**：股價跌破季線，長線趨勢偏弱。")

    # 2. 道氏理論 (均線排列)
    if latest['MA20'] > latest['MA60'] > latest['MA200']:
        long_score += 2
        long_reasons.append("🚀 **多頭排列**：月線 > 季線 > 年線，呈現最強勢的多頭型態。")

    # 3. 價值投資 (本益比 PE)
    if funds['PE']:
        pe = funds['PE']
        if pe < 15:
            long_score += 1
            long_reasons.append(f"💰 **價值低估**：本益比 {pe:.1f} 倍低於市場平均，具長線投資價值。")
        elif pe > 45:
            long_score -= 1
            long_reasons.append(f"⚠️ **估值過高**：本益比 {pe:.1f} 倍偏高，長線獲利空間壓縮。")

    return {
        "short": {"score": short_score, "reasons": short_reasons},
        "long": {"score": long_score, "reasons": long_reasons}
    }

def get_status_text(score):
    if score >= 3: return "🔥 強力買進 / 積極操作"
    elif score >= 1: return "🔴 偏多看待 / 持股續抱"
    elif score == 0: return "⚪ 區間震盪 / 觀望"
    elif score >= -2: return "🟢 偏空看待 / 逢高減碼"
    else: return "☠️ 強力賣出 / 避險空手"

# ==========================================
# 4. 前端介面
# ==========================================
st.title("🛡️ 專業級台股決策系統 (指標驗證版)")

with st.sidebar:
    st.header("🔍 股票搜尋")
    ticker_input = st.text_input("輸入代號 (如 2330)", "2330")
    ticker = ticker_input.upper().strip()
    if ticker.isdigit(): ticker += ".TW"
    
    st.markdown("---")
    st.info("""
    **指標參數驗證說明：**
    1. **KD 指標**：採用台股參數 (9, 3, 3)
    2. **MACD**：標準參數 (12, 26, 9)
    3. **策略來源**：WinSmart 雙指標共振、葛蘭碧八大法則
    """)

if ticker:
    with st.spinner("正在進行多重指標交叉驗證..."):
        df, info, funds = get_stock_data(ticker)
    
    if df is not None:
        # 1. 頂部基本資料
        st.subheader(f"{info.get('longName', ticker)} ({ticker.replace('.TW', '')})")
        last = df.iloc[-1]
        chg = last['Close'] - df.iloc[-2]['Close']
        pct = (chg / df.iloc[-2]['Close']) * 100
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("現價", f"{last['Close']:.2f}", f"{chg:.2f} ({pct:.2f}%)")
        c2.metric("成交量", f"{int(last['Volume']/1000)} 張")
        c3.metric("RSI (14)", f"{last['RSI']:.1f}")
        c4.metric("本益比 (PE)", f"{funds['PE']}" if funds['PE'] else "N/A")

        # 2. 邏輯分析結果
        result = analyze_logic(df, funds)
        
        st.markdown("### 🧭 長短期決策分析報告")
        col1, col2 = st.columns(2)
        
        # --- 短線區塊 ---
        with col1:
            s_score = result['short']['score']
            st.markdown(f"""
            <div class="outlook-card short-term">
                <div>⚡ <b>短線戰術 (1-2週)</b></div>
                <div class="big-score">{get_status_text(s_score)}</div>
                <div>依據：WinSmart KD+MACD、乖離率</div>
            </div>
            """, unsafe_allow_html=True)
            
            if result['short']['reasons']:
                for r in result['short']['reasons']:
                    st.markdown(f"<div class='signal-reason'>{r}</div>", unsafe_allow_html=True)
            else:
                st.info("目前短線無明確多空訊號 (盤整中)。")

        # --- 長線區塊 ---
        with col2:
            l_score = result['long']['score']
            st.markdown(f"""
            <div class="outlook-card long-term">
                <div>🌳 <b>長線戰略 (3-6月)</b></div>
                <div class="big-score">{get_status_text(l_score)}</div>
                <div>依據：葛蘭碧八大法則 (季線)、基本面</div>
            </div>
            """, unsafe_allow_html=True)
            
            if result['long']['reasons']:
                for r in result['long']['reasons']:
                    st.markdown(f"<div class='signal-reason'>{r}</div>", unsafe_allow_html=True)
            else:
                st.info("目前長線趨勢不明朗。")

        # 3. 驗證圖表 (視覺化證明)
        st.markdown("---")
        st.markdown("### 📊 指標訊號驗證圖")
        
        tab1, tab2 = st.tabs(["⚡ WinSmart 策略圖 (KD+MACD)", "🦁 葛蘭碧趨勢圖 (均線)"])
        
        with tab1:
            # 繪製 KD 與 MACD 
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                                row_heights=[0.5, 0.25, 0.25],
                                subplot_titles=("股價", "KD 指標 (9,3,3)", "MACD (12,26,9)"))
            
            # K線
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
            
            # KD
            fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='purple', width=1.5), name='K值'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='orange', width=1.5, dash='dot'), name='D值'), row=2, col=1)
            # 畫出 80/20 警戒線
            fig.add_hline(y=80, line_dash="dot", row=2, col=1, line_color="red", opacity=0.3)
            fig.add_hline(y=20, line_dash="dot", row=2, col=1, line_color="green", opacity=0.3)
            
            # MACD
            colors = ['red' if v > 0 else 'green' for v in df['OSC']]
            fig.add_trace(go.Bar(x=df.index, y=df['OSC'], marker_color=colors, name='MACD柱狀'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], line=dict(color='#E377C2', width=1), name='DIF'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DEM'], line=dict(color='#17BECF', width=1), name='DEM'), row=3, col=1)
            
            fig.update_layout(height=800, xaxis_rangeslider_visible=False, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            # 繪製葛蘭碧均線 
            fig2 = make_subplots(rows=1, cols=1)
            fig2.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'))
            
            # 關鍵均線
            fig2.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='月線 (短撐)'))
            fig2.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=2), name='季線 (生命線)'))
            fig2.add_trace(go.Scatter(x=df.index, y=df['MA200'], line=dict(color='purple', width=2), name='年線 (長趨勢)'))
            
            fig2.update_layout(height=600, xaxis_rangeslider_visible=False, title="葛蘭碧法則驗證：觀察股價是否站穩季線(藍線)")
            st.plotly_chart(fig2, use_container_width=True)

    else:
        st.error("查無資料，請確認股票代號。")
