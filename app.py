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
        if last['MACD_Hist'] > prev['MACD_
