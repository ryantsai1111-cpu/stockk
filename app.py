import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import datetime
import io
import re
from bs4 import BeautifulSoup

# ==========================================
# ⚙️ 網頁設定
# ==========================================
st.set_page_config(page_title="帥哥城 AI 投顧", page_icon="📈", layout="wide")

# ==========================================
# 🕵️‍♂️ 數據獲取層 (強力修正版)
# ==========================================

def get_yahoo_web_scraper(stock_id):
    """
    [修正版] 抓取財務數據 (本益比/殖利率)
    策略：遍歷所有 li 列表項目，使用 Regex 提取數字
    """
    headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        r = requests.get(url, headers=headers)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        
        data = {}
        # 抓中文名
        try:
            title = soup.title.text
            match = re.search(r'^(.+?)\(', title)
            data['Name'] = match.group(1).strip() if match else stock_id
        except: data['Name'] = stock_id

        # 抓數據 (針對 li 標籤進行精準打擊)
        def find_val(keyword):
            try:
                # Yahoo 數據通常放在 li 裡面
                for item in soup.find_all('li'):
                    if keyword in item.text:
                        # 使用 Regex 抓取數字 (包含小數點)
                        # 排除文字，只抓 12.34 或 -12.34
                        match = re.search(r'(-?\d+\.\d+|-?\d+)', item.text)
                        if match:
                            return float(match.group(0))
            except: pass
            return None

        data['PE'] = find_val("本益比")
        data['PB'] = find_val("股價淨值比")
        data['Yield'] = find_val("殖利率")
        if data['Yield'] is None: data['Yield'] = find_val("現金殖利率")
        
        return data
    except:
        return {'Name': stock_id, 'PE': None, 'PB': None, 'Yield': None}

def get_chinese_profile(stock_id):
    """
    [強力修正] 抓取中文公司簡介
    策略：直接鎖定 '主要業務' 關鍵字，抓取其後的內容
    """
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}/profile"
        headers = { "User-Agent": "Mozilla/5.0" }
        r = requests.get(url, headers=headers)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 策略 1: 尋找包含 "主要業務" 的區塊
        # Yahoo 的結構通常是：<div ...>主要業務</div><div ...>內容在這裡</div>
        # 我們找所有文字包含 "主要業務" 的元素
        targets = soup.find_all(string=re.compile("主要業務"))
        
        for target in targets:
            # 往上找父層，再找包含內容的區塊
            parent = target.parent
            # 嘗試找這個區塊附近的文字
            # 通常內容會在 parent 的下一個兄弟節點，或是 parent 的父層的文字
            container = parent.find_next('div')
            if container and len(container.text) > 10:
                return container.text.strip()
            
            # 備用：如果是舊版結構，可能直接在後面的 span 或 div
            next_sib = parent.find_next_sibling()
            if next_sib and len(next_sib.text) > 10:
                return next_sib.text.strip()

        # 策略 2: 如果上面失敗，抓 Meta Description 但要清洗
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta:
            desc = meta.get('content', '')
            # 清洗掉 Yahoo 的廣告詞
            if "提供公司基本資料" in desc:
                return "暫無詳細中文業務描述 (Yahoo 資料格式限制)"
            return desc
            
        return "暫無中文業務描述"
    except Exception as e:
        return "暫無資料"

def get_financial_data(stock_id, info):
    """[核心邏輯] 優先使用 yfinance"""
    pe = info.get('trailingPE')
    pb = info.get('priceToBook')
    div_yield = info.get('dividendYield')
    
    if div_yield: div_yield = div_yield * 100

    # 只要有缺漏，就啟動爬蟲補齊
    if pe is None or pb is None or div_yield is None:
        web_data = get_yahoo_web_scraper(stock_id)
        if pe is None: pe = web_data.get('PE')
        if pb is None: pb = web_data.get('PB')
        if div_yield is None: div_yield = web_data.get('Yield')
        
        if 'Name' in web_data and web_data['Name'] != stock_id:
            stock_name = web_data['Name']
        else:
            stock_name = info.get('longName', stock_id)
    else:
        stock_name = info.get('longName', stock_id)

    return {"Name": stock_name, "PE": pe, "PB": pb, "Yield": div_yield}

def get_mops_insider(stock_id):
    """MOPS 董監持股"""
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
    """Yahoo API 三大法人"""
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
# 📊 技術指標計算
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
# 📝 報告生成引擎
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
    
    # 呼叫修正後的中文爬蟲
    zh_summary = get_chinese_profile(stock_id)
    
    score = 50
    reasons = []
    
    # 評分邏輯
    price = today['Close']
    if price > today['MA20']: score += 10; reasons.append("股價站上月線，短多確立")
    else: score -= 10; reasons.append("股價跌破月線，短線整理")
    if price > today['MA60']: score += 10; reasons.append("站穩季線，長多格局")
    else: score -= 10
    
    chip_status = "數據不足"
    if chips:
        if chips['foreign'] > 0 and chips['trust'] > 0:
            score += 20; chip_status = "土洋合一"; reasons.append("法人同步買超，籌碼安定")
        elif chips['foreign'] < 0 and chips['trust'] < 0:
            score -= 20; chip_status = "法人棄守"; reasons.append("法人同步賣超，壓力沉重")
        elif chips['trust'] > 0:
            score += 10; chip_status = "投信認養"; reasons.append("投信護盤，下檔有撐")
        else: chip_status = "震盪整理"
            
    if insider and insider > 20: score += 5; reasons.append("大股東持股高，籌碼集中")
    
    score = max(0, min(100, score))
    
    if score >= 75: verdict = "強力買進 (Strong Buy)"; color = "green"
    elif score >= 55: verdict = "持有/觀望 (Hold)"; color = "orange"
    else: verdict = "賣出/避開 (Sell)"; color = "red"
    
    return {
        "id": stock_id,
        "name": fin_data['Name'],
        "price": price,
        "score": score,
        "verdict": verdict,
        "color": color,
        "reasons": reasons,
        "fin": fin_data,
        "chips": chips,
        "chip_status": chip_status,
        "insider": insider,
        "today": today,
        "info": info,
        "zh_summary": zh_summary
    }

# ==========================================
# 🖥️ UI 介面
# ==========================================

st.title("帥哥城 AI 投顧")
st.markdown("### 🚀 機構級投資分析報告書")

col1, col2 = st.columns([3, 1])
with col1:
    user_input = st.text_input("輸入代碼 (例如 2330, 2603)", "")
with col2:
    st.write("")
    st.write("")
    run_btn = st.button("生成報告", use_container_width=True)

if run_btn and user_input:
    stock_code = user_input.strip().upper()
    if stock_code.isdigit(): stock_code += ".TW"
    
    with st.spinner(f"正在分析 {stock_code} ..."):
        data = generate_full_analysis(stock_code)
        
    if data:
        st.header(f"1. 執行摘要：{data['name']} ({stock_code})")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("綜合信念評分", f"{data['score']} / 100")
        m2.metric("投資建議", data['verdict'].split(' ')[0])
        m3.metric("最新收盤價", f"{data['price']:.2f}")
        
        source_note = "數據來源：yfinance + 網頁爬蟲"
        m4.caption(source_note)
        
        st.info(f"""
        **關鍵見解**：
        目前評分為 **{data['score']} 分**，市場處於 **{data['chip_status']}** 階段。
        系統建議：**{data['verdict'].split('(')[0]}**。
        """)

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🏢 商業與基本面", 
            "💰 財務與估值", 
            "🏦 股權與籌碼", 
            "📈 技術分析", 
            "⚖️ 風險與展望"
        ])
        
        with tab1:
            st.subheader("業務背景 (Business Context)")
            # 這裡會顯示真正抓到的中文簡介，而不是 Yahoo 廣告詞
            if "Yahoo" in data['zh_summary']:
                st.warning("⚠️ 來源網站限制，無法取得完整中文描述。")
            else:
                st.write(data['zh_summary'])
            
            st.markdown("---")
            industry = data['info'].get('industry', 'N/A')
            sector = data['info'].get('sector', 'N/A')
            st.caption(f"**產業板塊**：{sector} > {industry}")
            
        with tab2:
            st.subheader("財務績效 (Financial Performance)")
            f1, f2, f3 = st.columns(3)
            # 數據處理：如果是 None 顯示 N/A，否則顯示數字
            pe_val = f"{data['fin']['PE']:.2f}" if data['fin']['PE'] is not None else "N/A"
            pb_val = f"{data['fin']['PB']:.2f}" if data['fin']['PB'] is not None else "N/A"
            yld_val = f"{data['fin']['Yield']:.2f}%" if data['fin']['Yield'] is not None else "N/A"
            
            f1.metric("本益比 (P/E)", pe_val)
            f2.metric("股價淨值比 (P/B)", pb_val)
            f3.metric("殖利率 (Yield)", yld_val)
            
            st.markdown("---")
            ef1, ef2, ef3 = st.columns(3)
            roe = data['info'].get('returnOnEquity', None)
            rev_growth = data['info'].get('revenueGrowth', None)
            gross_margin = data['info'].get('grossMargins', None)
            
            ef1.metric("ROE", f"{roe*100:.2f}%" if roe else "N/A")
            ef2.metric("營收成長率 (YoY)", f"{rev_growth*100:.2f}%" if rev_growth else "N/A")
            ef3.metric("毛利率", f"{gross_margin*100:.2f}%" if gross_margin else "N/A")

        with tab3:
            st.subheader("所有權與交易動態")
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**法人籌碼動向**：{data['chip_status']}")
                if data['chips']:
                    st.json(data['chips'])
                else:
                    st.warning("⚠️ 無法取得今日法人籌碼")
            with c2:
                st.write("**內部人持股**")
                if data['insider']:
                    st.metric("董監持股比例", f"{data['insider']}%")
                else:
                    st.write("暫無資料")

        with tab4:
            st.subheader("技術分析")
            t1, t2, t3 = st.columns(3)
            t1.metric("RSI (14)", f"{data['today']['RSI']:.2f}")
            t2.metric("MACD", f"{data['today']['MACD'] - data['today']['Signal']:.2f}")
            t3.metric("收盤價 vs 月線", f"{'站上 🔼' if data['price'] > data['today']['MA20'] else '跌破 🔻'}")

        with tab5:
            st.subheader("未來展望與風險")
            st.markdown(f"""
            **私人投資者最終評估**：
            本系統建議採取 **【{data['verdict']}】** 策略。
            請密切關注 **月線支撐 ({data['today']['MA20']:.2f})**，若跌破建議適度減碼。
            """)

    else:
        st.error(f"❌ 查無代碼 {stock_code}，請確認是否輸入正確。")
