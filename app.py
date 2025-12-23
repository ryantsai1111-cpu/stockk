import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import datetime
import io
import re
from bs4 import BeautifulSoup

# ==========================================
# ⚙️ 網頁設定區
# ==========================================
st.set_page_config(page_title="帥哥城 AI 投顧", page_icon="😎", layout="centered")

st.title("😎 帥哥城 AI 投顧 (網頁版)")
st.caption("🚀 自動化台股健檢：技術面 + 籌碼面 + 財報爬蟲 + 內部人持股")

# ==========================================
# 🕵️‍♂️ 數據抓取模組 (核心大腦)
# ==========================================

def get_yahoo_web_data(stock_id):
    """
    [網頁爬蟲] 抓取本益比、殖利率、中文股名
    修正：使用 Regex 強制提取數字，過濾 '河流圖' 等中文干擾
    """
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = { "User-Agent": "Mozilla/5.0" }
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, 'html.parser')
        data = {}
        
        # 1. 抓取中文股名
        try:
            title = soup.title.text
            # 標題格式通常是 "台積電(2330)..." -> 抓括號前的字
            match = re.search(r'^(.+?)\(', title)
            data['Name'] = match.group(1).strip() if match else stock_id
        except: data['Name'] = stock_id

        # 2. 抓取財務數據 (強制過濾中文)
        def find_val(keyword):
            try:
                for item in soup.find_all('li'):
                    if keyword in item.text:
                        # ✅ 只抓取數字 (包含小數點與負號)
                        match = re.search(r'(-?\d+\.\d+|-?\d+)', item.text)
                        if match: return match.group(0)
            except: pass
            return "N/A"

        data['PE'] = find_val("本益比")
        data['PB'] = find_val("股價淨值比")
        data['Yield'] = find_val("殖利率")
        if data['Yield'] == "N/A": data['Yield'] = find_val("現金殖利率")
        
        return data
    except: return {'Name': stock_id, 'PE': 'N/A', 'PB': 'N/A', 'Yield': 'N/A'}

def get_mops_insider(stock_id):
    """[MOPS 爬蟲] 抓取董監事持股比例"""
    try:
        clean_id = stock_id.replace(".TW", "").replace(".TWO", "")
        url = "https://mopsov.twse.com.tw/mops/web/ajax_t146sb05"
        now = datetime.datetime.now()
        year, month = now.year - 1911, now.month - 1
        if month == 0: month = 12; year -= 1
        
        payload = {'encodeURIComponent': '1', 'step': '1', 'firstin': '1', 'off': '1', 'co_id': clean_id, 'year': str(year), 'month': str(month)}
        r = requests.post(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'})
        
        # 使用 io.StringIO 避免 pandas 警告
        dfs = pd.read_html(io.StringIO(r.text))
        for df in dfs:
            df.columns = df.columns.astype(str)
            if '全體董監事持股合計' in df.to_string():
                val = df.iloc[-1].astype(str).str.extract(r'(\d+\.?\d*)').dropna().iloc[-1, 0]
                return float(val)
    except: return None

def get_chips_yahoo_api(stock_id):
    """[API] 抓取三大法人買賣超"""
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
# 🧠 核心邏輯 (計算與評分)
# ==========================================

def calculate_technicals(df):
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    return df

def generate_report(stock_id):
    # 1. 抓取歷史股價
    stock = yf.Ticker(stock_id)
    df = stock.history(period="1y")
    if df.empty: return None
    
    # 2. 計算指標
    df = calculate_technicals(df)
    today = df.iloc[-1]
    price = today['Close']
    
    # 3. 抓取外部數據
    chips = get_chips_yahoo_api(stock_id)
    insider = get_mops_insider(stock_id)
    web_data = get_yahoo_web_data(stock_id)
    
    # 4. 評分系統 (0-100)
    score = 50
    reasons = []
    
    # 技術面評分
    if price > today['MA20']: 
        score += 10
        reasons.append("📈 站上月線 (短線轉強)")
    else: 
        score -= 10
        reasons.append("📉 跌破月線 (短線轉弱)")
        
    if price > today['MA60']: 
        score += 10
        reasons.append("📈 站穩季線 (長多格局)")
    else: 
        score -= 10
        
    if today['MACD'] > today['Signal']: score += 5
    
    if today['RSI'] < 25: 
        score += 10
        reasons.append("💎 RSI 超賣 (醞釀反彈)")
    elif today['RSI'] > 75:
        score -= 5
        reasons.append("⚠️ RSI 過熱 (慎防回檔)")
    
    # 籌碼面評分
    chip_msg = "數據不足"
    if chips:
        if chips['foreign'] > 0 and chips['trust'] > 0: 
            score += 20
            chip_msg = "🔥 土洋合一 (主力做多)"
        elif chips['foreign'] < 0 and chips['trust'] < 0: 
            score -= 20
            chip_msg = "❄️ 法人棄守 (雙重賣壓)"
        elif chips['trust'] > 0: 
            score += 10
            chip_msg = "🛡️ 投信認養 (內資撐盤)"
        else: 
            chip_msg = "⚖️ 土洋對作 (震盪整理)"
            
    # 內部人加分
    if insider and insider > 20:
        score += 5
        reasons.append(f"👍 董監持股高 ({insider}%)")

    score = max(0, min(100, score))
    
    # 5. 最終判決
    if score >= 75: verdict = "🟢 強力買進"; color = "green"; action = "現在是佈局良機，建議分批進場。"
    elif score >= 55: verdict = "🟡 持有/中性"; color = "orange"; action = "不追高，拉回月線附近再考慮。"
    elif score >= 40: verdict = "🟠 觀望"; color = "orange"; action = "趨勢不明，多看少做。"
    else: verdict = "🔴 賣出/避開"; color = "red"; action = "上方壓力大，建議停損或觀望。"
    
    return {
        "name": web_data.get('Name', stock_id),
        "price": price,
        "score": score,
        "verdict": verdict,
        "color": color,
        "action": action,
        "chip_msg": chip_msg,
        "chips": chips,
        "insider": insider,
        "web_data": web_data,
        "today": today,
        "reasons": reasons
    }

# ==========================================
# 🖥️ UI 介面互動區
# ==========================================

# 輸入框
stock_code_input = st.text_input("請輸入股票代碼 (支援台股)", placeholder="例如: 2330, 2603, 0050")

if st.button("開始分析", use_container_width=True):
    if not stock_code_input:
        st.warning("請輸入代碼！")
    else:
        # 自動補上 .TW
        target_code = stock_code_input.strip().upper()
        if target_code.isdigit(): target_code += ".TW"
        
        with st.spinner(f"正在連線 Yahoo 與 MOPS 分析 {target_code} ..."):
            data = generate_report(target_code)
            
        if data:
            # --- 顯示結果 ---
            st.markdown(f"## {data['name']} ({target_code})")
            
            # 第一排：評分與判決
            c1, c2 = st.columns(2)
            c1.metric("🏆 綜合評分", f"{data['score']} 分")
            c2.markdown(f"### 🚦 :{data['color']}[{data['verdict']}]")
            
            st.info(f"💡 **操作指引**：{data['action']}")
            
            st.divider()
            
            # 第二排：詳細數據
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("##### 📊 技術面")
                st.write(f"現價：**{data['price']:.1f}**")
                st.write(f"月線：{data['today']['MA20']:.1f}")
                st.write(f"RSI：{data['today']['RSI']:.1f}")
                
            with col2:
                st.markdown("##### 💰 基本面")
                st.write(f"本益比：{data['web_data']['PE']}")
                st.write(f"殖利率：{data['web_data']['Yield']}%")
                st.write(f"股價淨值比：{data['web_data']['PB']}")
                
            with col3:
                st.markdown("##### 🏦 籌碼面")
                st.write(f"狀態：**{data['chip_msg']}**")
                st.write(f"董監持股：{data['insider']}%")
            
            # 籌碼明細
            if data['chips']:
                st.caption(f"三大法人近一日：外資 {data['chips']['foreign']} | 投信 {data['chips']['trust']} | 自營 {data['chips']['dealer']} (張)")

            st.divider()
            
            # 評分理由
            st.subheader("📝 關鍵評分理由")
            for r in data['reasons']:
                st.write(f"- {r}")
                
        else:
            st.error(f"❌ 查無代碼 {target_code}，請確認是否輸入正確。")
