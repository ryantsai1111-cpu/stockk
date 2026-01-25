import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. 基礎設定與輔助函數
# ==========================================
st.set_page_config(page_title="台股分析助手", layout="wide", page_icon="📈")

def format_ticker(user_input):
    """自動加上 .TW，讓使用者只要輸入 2330"""
    user_input = user_input.upper().strip()
    # 移除常見的錯誤符號
    user_input = user_input.replace("台積電", "2330").replace("長榮", "2603")
    
    if user_input.isdigit():
        return f"{user_input}.TW"
    return user_input

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
            "eps": info.get('trailingEps', 'N/A')
        }
        # 格式化殖利率
        if data['yield'] and isinstance(data['yield'], (int, float)):
             data['yield'] = f"{data['yield']*100:.2f}%"
        
        return data, stock
    except Exception as e:
        return None, None

def calculate_macd(df, fast=12, slow=26, signal=9):
    """手動計算 MACD (不依賴 ta 套件)"""
    exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

# ==========================================
# 2. 前端介面
# ==========================================
st.title("📈 台股個股分析儀表板")

with st.sidebar:
    st.header("設定")
    ticker_input = st.text_input("輸入股票代號", "2330")
    ticker = format_ticker(ticker_input)
    st.info(f"正在查詢: {ticker}")

if ticker:
    fund_data, stock = get_fundamentals(ticker)
    
    if fund_data:
        # 顯示基本面數據
        st.subheader(f"{fund_data['name']} ({ticker})")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("本益比 (PE)", fund_data['pe_ratio'])
        col2.metric("EPS", fund_data['eps'])
        col3.metric("殖利率", fund_data['yield'])
        col4.metric("ROE", fund_data['roe'])
        
        # 抓取 K 線資料
        df = stock.history(period="1y")
        
        if not df.empty:
            # 計算指標
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()
            
            # 手算布林通道
            std = df['Close'].rolling(window=20).std()
            df['BB_Upper'] = df['MA20'] + (std * 2)
            df['BB_Lower'] = df['MA20'] - (std * 2)
            
            # 手算 MACD
            df['DIF'], df['DEM'], df['MACD_Hist'] = calculate_macd(df)

            # 繪圖
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
            
            # 布林通道
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=0.5, dash='dot'), name='布林上緣'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=0.5, dash='dot'), name='布林下緣'), row=1, col=1)

            # MACD
            colors = ['red' if v >= 0 else 'green' for v in df['MACD_Hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=colors, name='MACD柱狀'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], line=dict(color='orange', width=1), name='DIF (快)'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DEM'], line=dict(color='blue', width=1), name='DEM (慢)'), row=2, col=1)

            fig.update_layout(xaxis_rangeslider_visible=False, height=600)
            st.plotly_chart(fig, use_container_width=True)
            
    else:
        st.error("找不到該股票資訊，請確認代號。")
