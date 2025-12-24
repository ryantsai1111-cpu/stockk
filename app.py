import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import datetime
import io
import re
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# ==========================================
# ⚙️ 網頁設定
# ==========================================
st.set_page_config(page_title="帥哥城 AI 投顧", page_icon="📈", layout="wide")

# 建立 Session 維持連線
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# ==========================================
# 🛠️ 工具函式
# ==========================================
def translate_to_chinese(text):
    try:
        if not text or len(text) < 5: return "暫無詳細業務描述。"
        return GoogleTranslator(source='auto', target='zh-TW').translate(text)
    except: return text

# ==========================================
# 🕵️‍♂️ 數據獲取層 (FinMind + Yahoo)
# ==========================================

def get_finmind_equity(stock_id):
    """
    [新增] 使用 FinMind API 抓取集保分佈
    優點：官方 API，穩定不被鎖
    內容：400張以上大戶比例、總股東人數
    """
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "")
    
    # 設定抓取過去 90 天資料，確保能跨週比較
    start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
    
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {
        "dataset": "TaiwanStockHoldingSharesPer",
        "data_id": clean_id,
        "start_date": start_date
    }
    
    try:
        r = requests.get(url, params=parameter, timeout=10)
        data = r.json().get('data', [])
        
        if not data: return None
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        
        # 取得所有可用日期
        dates = sorted(df['date'].unique())
        if len(dates) < 2: return None 
        
        # 取最近兩期 (本週 vs 上週)
        latest_date = dates[-1]
        prev_date = dates[-2]
        
        df_latest = df[df['date'] == latest_date]
        df_prev = df[df['date'] == prev_date]
        
        # 計算總股東人數
        holders_now = df_latest['numberOfShareholders'].sum()
        holders_prev = df_prev['numberOfShareholders'].sum()
        
        # 計算 400 張以上大戶比例
        # FinMind 等級 16 對應 400,001-600,000 股
        # 我們加總等級 >= 16 的比例 (嚴格定義 > 400張)
        def calc_big_percent(dframe):
            dframe['HoldingSharesLevel'] = pd.to_numeric(dframe['HoldingSharesLevel'], errors='coerce')
            # 16級以上是大戶
            big_df = dframe[dframe['HoldingSharesLevel'] >= 16]
            return big_df['percentage'].sum()
            
        big_now = calc_big_percent(df_latest)
        big_prev = calc_big_percent(df_prev)
        
        return {
            "source": "FinMind API",
            "date": latest_date.strftime('%Y-%m-%d'),
            "big_percent": big_now,
            "big_change": big_now - big_prev,
            "holders": int(holders_now),
            "holders_change": int(holders_now) - int(holders_prev)
        }
        
    except Exception as e:
        print(f"FinMind Error: {e}")
        return None

def get_yahoo_financial_ratios(stock_id):
    """Yahoo 財務比率爬蟲 (穩定版)"""
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}/financial-ratios"
        r = session.get(url, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        text_content = soup.get_text()
        
        data = {}
        def extract_percent(keyword):
            pattern = re.compile(f"{keyword}.*?(-?\d+\.?\d+)%")
            match = pattern.search(text_content)
            return float(match.group(1)) if match else None

        data['GrossMargin'] = extract_percent("毛利率")
        data['OpMargin'] = extract_percent("營業利益率")
        data['NetMargin'] = extract_percent("稅後淨利率")
        data['ROE'] = extract_percent("股東權益報酬率")
        data['ROA'] = extract_percent("資產報酬率")
        
        def extract_val(keyword):
            pattern = re.compile(f"{keyword}.*?(-?\d+\.?\d+)")
            match = pattern.search(text_content)
            return float(match.group(1)) if match else None
            
        data['EPS'] = extract_val("每股盈餘")
        data['BPS'] = extract_val("每股淨值")
        
        return data
    except: return {}

def get_yahoo_web_scraper(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        r = session.get(url, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        data = {}
        try:
            title = soup.title.text
            match = re.search(r'^(.+?)\(', title)
            data['Name'] = match.group(1).strip() if match else stock_id
        except: data['Name'] = stock_id

        def search_val(keyword):
            try:
                for item in soup.find_all('li'):
                    if keyword in item.text:
                        match = re.search(r'(-?\d+\.\d+|-?\d+)', item.text)
                        if match: return float(match.group(0))
            except: pass
            return None

        data['PE'] = search_val("本益比")
        data['PB'] = search_val("股價淨值比")
        data['Yield'] = search_val("殖利率")
        if data['Yield'] is None: data['Yield'] = search_val("現金殖利率")
        return data
    except: return {'Name': stock_id, 'PE': None, 'PB': None, 'Yield': None}

def get_financial_data(stock_id, info):
    pe = info.get('trailingPE')
    pb = info.get('priceToBook')
    div_yield = info.get('dividendYield')
    if div_yield: div_yield = div_yield * 100

    if pe is None or pb is None or div_yield is None:
        web_data = get_yahoo_web_scraper(stock_id)
        if pe is None: pe = web_data.get('PE')
        if pb is None: pb = web_data.get('PB')
        if div_yield is None: div_yield = web_data.get('Yield')
        stock_name = web_data.get('Name', stock_id) if 'Name' in web_data else info.get('longName', stock_id)
    else:
        stock_name = info.get('longName', stock_id)
    return {"Name": stock_name, "PE": pe, "PB": pb, "Yield": div_yield}

def get_mops_insider(stock_id):
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "")
    url = "https://mopsov.twse.com.tw/mops/web/ajax_t146sb05"
    now = datetime.datetime.now()
    for i in range(1, 4):
        try:
            check_date = now - datetime.timedelta(days=30 * i)
            year, month = check_date.year - 1911, check_date.month
            payload = {'encodeURIComponent': '1', 'step': '1', 'firstin': '1', 'off': '1', 'co_id': clean_id, 'year': str(year), 'month': str(month)}
            r = requests.post(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'})
            dfs = pd.read_html(io.StringIO(r.text))
            for df in dfs:
                df.columns = df.columns.astype(str)
                if '全體董監事持股合計' in df.to_string():
                    val = df.iloc[-1].astype(str).str.extract(r'(\d+\.?\d*)').dropna().iloc[-1, 0]
                    return float(val)
        except: continue
    return None

def get_chips_yahoo_api(stock_id):
    try:
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.3MajorTrade:K?symbol={stock_id}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        if 'data' in data and 'list' in data['data'] and len(data['data']['list']) > 0:
            latest = data['data']['list'][0]
            return {
                'foreign': int(latest.get('foreignDiff', 0)) // 1000,
                'trust': int(latest.get('investmentTrustDiff', 0)) // 1000,
                'dealer': int(latest.get('dealerDiff', 0)) // 1000
            }
    except: return None

# ==========================================
# 📊 技術指標
# ==========================================
def calculate_technicals(df):
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

# ==========================================
# 📝 報告生成引擎 (v12.0 Final)
# ==========================================
def generate_full_analysis(stock_id):
    stock = yf.Ticker(stock_id)
    df = stock.history(period="1y")
    if df.empty: return None
    
    info = stock.info
    df = calculate_technicals(df)
    today = df.iloc[-1]
    
    fin_data = get_financial_data(stock_id, info)
    chips = get_chips_yahoo_api(stock_id)
    insider = get_mops_insider(stock_id)
    
    # ✅ 1. FinMind API 抓籌碼
    finmind_chip = get_finmind_equity(stock_id)
    
    # ✅ 2. Yahoo 財務比率爬蟲
    adv_fin = get_yahoo_financial_ratios(stock_id)
    
    # 補強財務數據
    if not adv_fin.get('GrossMargin'):
        def pct(v): return v*100 if v else None
        adv_fin = {
            'GrossMargin': pct(info.get('grossMargins')),
            'OpMargin': pct(info.get('operatingMargins')),
            'NetMargin': pct(info.get('profitMargins')),
            'ROE': pct(info.get('returnOnEquity')),
            'ROA': pct(info.get('returnOnAssets')),
            'EPS': info.get('trailingEps'),
            'BPS': info.get('bookValue')
        }
        fin_source = "yfinance (API)"
    else:
        fin_source = "Yahoo 股市 (Crawler)"

    raw_summary = info.get('longBusinessSummary', '')
    zh_summary = translate_to_chinese(raw_summary)
    
    # --- 評分 ---
    score = 50
    reasons = []
    
    if today['Close'] > today['MA20']: score += 10; reasons.append("股價站上月線，短多確立")
