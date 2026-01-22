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
        reasons.append("❌ **[道氏理論]**：空頭
