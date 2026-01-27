import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from ta.trend import MACD, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands
import time

# ==========================================
# 1. 頁面配置
# ==========================================
st.set_page_config(page_title="台股全方位戰情室", layout="wide", page_icon="🛡️")

# CSS 樣式：恢復長短期卡片設計
st.markdown("""
<style>
    .outlook-card {padding: 15px; border-radius: 12px; margin-bottom: 15px; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}
    .short-term {background: linear-gradient(135deg, #FF512F 0%, #DD2476 100%);} /* 紅色系 */
    .long-term {background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);} /* 綠色系 */
    .big-score {font-size: 28px; font-weight: bold; border-bottom: 2px solid rgba(255,255,255,0.3); padding-bottom: 10px; margin-bottom: 10px;}
    .signal-reason {background-color: rgba(255,255,255,0.2); padding: 5px 10px; border-radius: 5px; margin-top: 5px; font-size: 14px;}
    .badge {background-color: #333; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 12px;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 數據核心 (雙軌抓取：同時抓日線與分時)
# ==========================================
def calculate_indicators(df, is_daily=True):
    """統一計算指標的函數"""
    if df is None or df.empty: return None
    
    # 1. 均線
    df['MA5'] = SMAIndicator(df['Close'], window=5).sma_indicator()
    df['MA20'] = SMAIndicator(df['Close'], window=20).sma_indicator()
    df['MA60'] = SMAIndicator(df['Close'], window=60).sma_indicator()
    if is_daily:
        df['MA200'] = SMAIndicator(df['Close'], window=200).sma_indicator() # 只有日線算年線

    # 2. KD (9,3,3) - 台股標準
    kd = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=9, smooth_window=3)
    df['K'] = kd.stoch()
    df['D'] = kd.stoch_signal()

    # 3. MACD (12,26,9) - 國際標準
    macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
    df['DIF'] = macd.macd()
    df['DEM'] = macd.macd_signal()
    df['OSC'] = macd.macd_diff()

    # 4. RSI (14)
    df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
    
    # 5. 布林通道
    bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['BB_H'] = bb.bollinger_hband()
    df['BB_L'] = bb.bollinger_lband()
    
    return df

def get_hybrid_data(ticker, use_realtime=False):
    """
    混合抓取模式：
    - 總是抓取 '日線' (做長線分析)
    - 如果 use_realtime=True，額外抓取 '60分K' (做短線分析)
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 1. 抓日線 (Long-term Data)
        df_daily = stock.history(period="2y", interval="1d")
        df_daily = calculate_indicators(df_daily, is_daily=True)
        
        # 2. 抓短線 (Short-term Data)
        if use_realtime:
            # 盤中看 60分K
            df_short = stock.history(period="1mo", interval="60m")
            df_short = calculate_indicators(df_short, is_daily=False)
            data_source_text = "盤中 60分K (即時)"
        else:
            # 收盤看 日K
            df_short = df_daily.copy() # 短線分析也用日線
            data_source_text = "收盤 日K線"

        # 3. 基本面
        info = stock.info
        fundamentals = {
            "PE": info.get('trailingPE', None),
            "PB": info.get('priceToBook', None)
        }
        
        return df_daily, df_short, info, fundamentals, data_source_text

    except Exception as e:
        st.error(f"數據連線錯誤: {e}")
        return None, None, None, None, None

# ==========================================
# 3. 邏輯分析 (長短分離)
# ==========================================
def analyze_structure(df_daily, df_short, funds):
    # --- A. 短線戰術 (使用 df_short) ---
    # 這裡的數據可能是 60分K (盤中) 或 日K (盤後)
    latest_s = df_short.iloc[-1]
    prev_s = df_short.iloc[-2]
    
    s_score = 0
    s_reasons = []
    
    # 1. KD + MACD 共振 (WinSmart)
    if latest_s['K'] > latest_s['D'] and latest_s['OSC'] > 0:
        if prev_s['K'] < prev_s['D'] or prev_s['OSC'] < 0:
            s_score += 3
            s_reasons.append("★ **買進訊號**：KD金叉且MACD翻紅 (雙指標共振)。")
        else:
            s_score += 1
            s_reasons.append("📈 **趨勢偏多**：短線指標維持多頭排列。")
    elif latest_s['K'] < latest_s['D'] and latest_s['OSC'] < 0:
        s_score -= 3
        s_reasons.append("📉 **賣出訊號**：KD死叉且MACD綠柱 (雙指標空頭)。")
        
    # 2. 均線乖離 (短線看 MA20 布林中軌)
    if latest_s['Close'] > latest_s['MA20']:
        s_score += 1
        s_reasons.append("⚡ **支撐確認**：股價位於 20MA 之上，短線強勢。")
    else:
        s_score -= 1
        s_reasons.append("⚠️ **破線轉弱**：跌破 20MA 支撐。")

    # 3. RSI
    if latest_s['RSI'] > 80:
        s_score -= 1
        s_reasons.append("🔥 **短線過熱**：RSI > 80，提防盤中回檔。")
    elif latest_s['RSI'] < 20:
        s_score += 2
        s_reasons.append("💎 **短線超賣**：RSI < 20，醞釀反彈。")

    # --- B. 長線戰略 (永遠使用 df_daily) ---
    latest_l = df_daily.iloc[-1]
    
    l_score = 0
    l_reasons = []
    
    # 1. 葛蘭碧法則 (看季線 MA60)
    if latest_l['Close'] > latest_l['MA60']:
        l_score += 2
        l_reasons.append("🦁 **長多格局**：股價站穩季線 (生命線)。")
    else:
        l_score -= 2
        l_reasons.append("🐻 **長空格局**：股價落於季線之下。")
        
    # 2. 牛熊分界 (看年線 MA200)
    if latest_l['Close'] > latest_l['MA200']:
        l_score += 1
        l_reasons.append("✅ **牛市區域**：站上年線 (200MA)。")
        
    # 3. 價值面 (PE)
    if funds['PE']:
        if funds['PE'] < 15:
            l_score += 1
            l_reasons.append(f"💰 **價值低估**：本益比 {funds['PE']:.1f} 倍，長線便宜。")
        elif funds['PE'] > 45:
            l_score -= 1
            l_reasons.append(f"⚠️ **估值過高**：本益比 {funds['PE']:.1f} 倍，長線風險增高。")

    return {
        "short": {"score": s_score, "reasons": s_reasons},
        "long": {"score": l_score, "reasons": l_reasons}
    }

def get_status_text(score):
    if score >= 3: return "🔥 強力買進"
    elif score >= 1: return "🔴 偏多操作"
    elif score == 0: return "⚪ 觀望整理"
    elif score >= -2: return "🟢 偏空看待"
    else: return "☠️ 強力賣出"

# ==========================================
# 4. 前端介面
# ==========================================
st.title("🛡️ 台股全方位戰情室")

with st.sidebar:
    st.header("⚙️ 模式設定")
    ticker_input = st.text_input("股票代號", "2330")
    ticker = ticker_input.upper().strip()
    if ticker.isdigit(): ticker += ".TW"
    
    st.markdown("---")
    st.markdown("### 🕒 資料來源模式")
    # 讓使用者選擇是否要開啟「盤中即時」
    mode_select = st.radio("選擇模式", ["收盤分析 (日線)", "盤中即時 (60分K)"], index=0)
    use_realtime = True if "盤中" in mode_select else False
    
    st.markdown("---")
    if st.button("🔄 強制刷新報價"):
        st.cache_data.clear()
        st.rerun()

if ticker:
    # 抓取資料 (Spinner 只在第一次出現)
    with st.spinner("正在進行長短期雙軌運算..."):
        df_daily, df_short, info, funds, source_text = get_hybrid_data(ticker, use_realtime)

    if df_daily is not None and df_short is not None:
        # 1. 報價資訊
        st.subheader(f"{info.get('longName', ticker)} ({ticker.replace('.TW', '')})")
        
        last_price = df_short.iloc[-1]['Close']
        try:
            # 嘗試計算漲跌 (如果盤中資料不足，用昨收)
            prev_close = df_daily.iloc[-2]['Close']
            chg = last_price - prev_close
            pct = (chg / prev_close) * 100
        except:
            chg = 0; pct = 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("現價", f"{last_price:.2f}", f"{chg:.2f} ({pct:.2f}%)")
        c2.metric("分析數據源", source_text, delta="Live" if use_realtime else "Close", delta_color="off")
        c3.metric("KD (K值)", f"{df_short.iloc[-1]['K']:.1f}")
        c4.metric("本益比", f"{funds['PE']}" if funds['PE'] else "N/A")

        # 2. 邏輯分析 (長短分離)
        analysis = analyze_structure(df_daily, df_short, funds)
        
        st.markdown("### 🧭 長短期決策分析")
        
        col_s, col_l = st.columns(2)
        
        # 左邊：短線戰術
        with col_s:
            score = analysis['short']['score']
            st.markdown(f"""
            <div class="outlook-card short-term">
                <div>⚡ <b>短線戰術 ({'60分K' if use_realtime else '日K'})</b></div>
                <div class="big-score">{get_status_text(score)} ({score})</div>
                <div>依據：WinSmart KD+MACD</div>
            </div>
            """, unsafe_allow_html=True)
            for r in analysis['short']['reasons']:
                st.markdown(f"<div class='signal-reason'>{r}</div>", unsafe_allow_html=True)

        # 右邊：長線戰略
        with col_l:
            score = analysis['long']['score']
            st.markdown(f"""
            <div class="outlook-card long-term">
                <div>🌳 <b>長線戰略 (日K線趨勢)</b></div>
                <div class="big-score">{get_status_text(score)} ({score})</div>
                <div>依據：葛蘭碧法則 (季線/年線)</div>
            </div>
            """, unsafe_allow_html=True)
            for r in analysis['long']['reasons']:
                st.markdown(f"<div class='signal-reason'>{r}</div>", unsafe_allow_html=True)

        # 3. 圖表區 (分頁顯示)
        st.markdown("---")
        tab1, tab2 = st.tabs(["📉 短線動能圖 (KD+MACD)", "📊 長線趨勢圖 (均線)"])
        
        with tab1:
            st.caption(f"圖表週期：{source_text}")
            # 畫短線圖 (可能是 60m 也可能是 日線)
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25])
            fig.add_trace(go.Candlestick(x=df_short.index, open=df_short['Open'], high=df_short['High'], low=df_short['Low'], close=df_short['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_short.index, y=df_short['MA20'], line=dict(color='orange', width=1), name='20MA'), row=1, col=1)
            
            # KD
            fig.add_trace(go.Scatter(x=df_short.index, y=df_short['K'], line=dict(color='purple'), name='K'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_short.index, y=df_short['D'], line=dict(color='orange', dash='dot'), name='D'), row=2, col=1)
            fig.add_hline(y=80, line_dash="dot", row=2, col=1, line_color="red")
            fig.add_hline(y=20, line_dash="dot", row=2, col=1, line_color="green")
            
            # MACD
            colors = ['red' if v > 0 else 'green' for v in df_short['OSC']]
            fig.add_trace(go.Bar(x=df_short.index, y=df_short['OSC'], marker_color=colors, name='MACD'), row=3, col=1)
            
            fig.update_layout(height=600, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            st.caption("圖表週期：日 K 線 (固定)")
            # 畫長線圖 (永遠是日線)
            fig2 = make_subplots(rows=1, cols=1)
            fig2.add_trace(go.Candlestick(x=df_daily.index, open=df_daily['Open'], high=df_daily['High'], low=df_daily['Low'], close=df_daily['Close'], name='K線'))
            fig2.add_trace(go.Scatter(x=df_daily.index, y=df_daily['MA60'], line=dict(color='blue', width=2), name='季線 (60MA)'))
            fig2.add_trace(go.Scatter(x=df_daily.index, y=df_daily['MA200'], line=dict(color='purple', width=2), name='年線 (200MA)'))
            
            fig2.update_layout(height=500, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig2, use_container_width=True)

    else:
        st.error("查無資料，請確認代號。")

