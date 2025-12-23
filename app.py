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

# ==========================================
# 🛠️ 工具函式
# ==========================================
def translate_to_chinese(text):
    try:
        if not text or len(text) < 5: return "暫無詳細業務描述。"
        return GoogleTranslator(source='auto', target='zh-TW').translate(text)
    except: return text

# ==========================================
# 🕵️‍♂️ 數據獲取層 (HiStock + Yahoo API)
# ==========================================

def get_histock_chips(stock_id):
    """
    [替代 Goodinfo] 從 HiStock (嗨投資) 抓取集保分佈
    優點：不易被封鎖，且格式整齊
    """
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "")
    url = f"https://histock.tw/stock/large.aspx?no={clean_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        # HiStock 通常用 pandas 就能直接讀取表格
        dfs = pd.read_html(io.StringIO(r.text))
        
        for df in dfs:
            # 尋找包含 "400張" 和 "股東人數" 的表格
            df_str = df.to_string()
            if "400張" in df_str and "股東人數" in df_str:
                # HiStock 的表格通常有「日期」或「週別」在第一欄
                # 我們取最近兩筆 (Index 0=本週, 1=上週)
                latest = df.iloc[0]
                prev = df.iloc[1]
                
                # 欄位名稱可能包含 %, 所以我們用關鍵字找欄位
                cols = df.columns
                
                # 找 "400張" 比例的欄位
                big_col = [c for c in cols if "400張" in str(c) and "%" in str(c)]
                # 找 "股東人數" 的欄位
                holders_col = [c for c in cols if "人數" in str(c)]
                date_col = [c for c in cols if "期" in str(c) or "周" in str(c) or "日" in str(c)]
                
                if big_col and holders_col:
                    curr_big = float(str(latest[big_col[0]]).replace('%', ''))
                    prev_big = float(str(prev[big_col[0]]).replace('%', ''))
                    
                    curr_hold = int(latest[holders_col[0]])
                    prev_hold = int(prev[holders_col[0]])
                    
                    date_str = str(latest[date_col[0]]) if date_col else "本週"
                    
                    return {
                        "source": "HiStock",
                        "date": date_str,
                        "big_percent": curr_big,
                        "big_change": curr_big - prev_big,
                        "holders": curr_hold,
                        "holders_change": curr_hold - prev_hold
                    }
    except Exception as e:
        print(f"HiStock Error: {e}")
        return None
    return None

def get_yahoo_financials_adv(stock_id):
    """
    [替代 Goodinfo] 從 Yahoo API 抓取進階財報 (獲利能力)
    """
    try:
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.Revenues:K?symbol={stock_id}"
        # Yahoo 的財報 API 比較隱密，我們改抓基本的 Profile 頁面爬蟲，這最穩
        # 但為了豐富度，我們這裡用 yfinance 的 info 補強，加上網頁爬蟲
        
        # 啟動網頁爬蟲抓取 "財務比率"
        url_profile = f"https://tw.stock.yahoo.com/quote/{stock_id}/profile"
        headers = { "User-Agent": "Mozilla/5.0" }
        r = requests.get(url_profile, headers=headers)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        data = {}
        
        def find_val_li(keyword):
            try:
                for item in soup.find_all('div'):
                    if keyword in item.text:
                        # 找鄰近的數值
                        match = re.search(r'(-?\d+\.\d+|-?\d+)%?', item.text)
                        if match: return float(match.group(1))
            except: pass
            return None
            
        # Yahoo 網頁改版後，數據可能在不同位置，我們用最保險的 yfinance 做基底
        return None # 讓主程式切換到 yfinance
        
    except: return None

def get_financials_hybrid(stock_id, info):
    """
    [混合獲取] 財務三率與經營績效
    策略：
    1. 主要依賴 yfinance (最穩定，不會被擋)
    2. 補充 Yahoo 網頁爬蟲
    """
    data = {}
    source = "Yahoo/yfinance"
    
    # 數值轉換：yfinance 給的是小數 (0.5)，我們要轉百分比 (50.0)
    def pct(val): return val * 100 if val is not None else None
    
    # 從 yfinance info 獲取 (最穩)
    data['GrossMargin'] = pct(info.get('grossMargins'))
    data['OpMargin'] = pct(info.get('operatingMargins'))
    data['NetMargin'] = pct(info.get('profitMargins'))
    data['ROE'] = pct(info.get('returnOnEquity'))
    data['ROA'] = pct(info.get('returnOnAssets'))
    data['EPS'] = info.get('trailingEps')
    data['BPS'] = info.get('bookValue')
    
    # 如果 yfinance 缺資料 (台股常發生)，啟動 Yahoo 網頁爬蟲補救
    if data['GrossMargin'] is None or data['ROE'] is None:
        try:
            # 簡單爬取 Yahoo 股市的 "基本資料" 頁面
            url = f"https://tw.stock.yahoo.com/quote/{stock_id}/profile"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=5)
            text = r.text
            
            def search_regex(kw):
                # 尋找 "ROE 20.5%" 這樣的格式
                match = re.search(f'{kw}.*?(-?\d+\.?\d+)%', text)
                return float(match.group(1)) if match else None

            if data['ROE'] is None: data['ROE'] = search_regex("ROE")
            if data['ROA'] is None: data['ROA'] = search_regex("ROA")
            source = "Yahoo Web"
        except: pass

    return data, source

def get_yahoo_web_scraper(stock_id):
    headers = { "User-Agent": "Mozilla/5.0" }
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        r = requests.get(url, headers=headers, timeout=5)
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
# 📝 報告生成引擎 (v9.0 Integration)
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
    
    # ✅ 1. 換成 HiStock 抓籌碼 (避開 Goodinfo 封鎖)
    histock_chip = get_histock_chips(stock_id)
    
    # ✅ 2. 換成 Yahoo/yfinance 混合抓財務 (避開 Goodinfo 封鎖)
    adv_fin, fin_source = get_financials_hybrid(stock_id, info)
    
    raw_summary = info.get('longBusinessSummary', '')
    zh_summary = translate_to_chinese(raw_summary)
    
    # --- 評分系統 ---
    score = 50
    reasons = []
    
    # 技術面
    if today['Close'] > today['MA20']: score += 10; reasons.append("股價站上月線，短多確立")
    else: score -= 10; reasons.append("股價跌破月線，短線整理")
    if today['Close'] > today['MA60']: score += 10; reasons.append("站穩季線，長多格局")
    else: score -= 10
    
    # 基本面 (Yahoo Hybrid)
    if adv_fin.get('GrossMargin') and adv_fin['GrossMargin'] > 30:
        score += 5; reasons.append(f"毛利率高 ({adv_fin['GrossMargin']:.1f}%)")
    if adv_fin.get('ROE') and adv_fin['ROE'] > 15:
        score += 5; reasons.append(f"ROE 優異 ({adv_fin['ROE']:.1f}%)")
            
    # 籌碼面
    chip_status = "數據不足"
    if chips:
        if chips['foreign'] > 0 and chips['trust'] > 0: score += 15; chip_status = "土洋合一"; reasons.append("法人同步買超")
        elif chips['foreign'] < 0 and chips['trust'] < 0: score -= 15; chip_status = "法人棄守"; reasons.append("法人同步賣超")
        elif chips['trust'] > 0: score += 10; chip_status = "投信認養"
    
    if histock_chip:
        if histock_chip['big_change'] > 0: score += 10; reasons.append("大戶持股增加")
        elif histock_chip['big_change'] < -0.2: score -= 10; reasons.append("大戶持股鬆動")
            
    if insider and insider > 20: score += 5; reasons.append("董監持股高")
    score = max(0, min(100, score))
    
    if score >= 75: verdict = "強力買進 (Strong Buy)"; color = "green"
    elif score >= 55: verdict = "持有/觀望 (Hold)"; color = "orange"
    else: verdict = "賣出/避開 (Sell)"; color = "red"
    
    # --- 未來展望 (邏輯生成) ---
    outlook_text = {"catalysts": [], "risks": [], "thesis": ""}
    
    # 催化劑
    if histock_chip and histock_chip['big_change'] > 0: outlook_text["catalysts"].append(f"**籌碼沉澱**：大戶持股本週增加 {histock_chip['big_change']:.2f}%，主力吸籌明顯。")
    if adv_fin.get('GrossMargin', 0) > 40: outlook_text["catalysts"].append(f"**護城河優勢**：毛利率達 {adv_fin['GrossMargin']:.1f}%，顯示產品具備強大定價權。")
    if chips and chips['trust'] > 0: outlook_text["catalysts"].append("**投信作帳**：投信近期買超，季底作帳行情可期。")
    if today['Close'] > today['MA60']: outlook_text["catalysts"].append("**多頭架構**：股價位於季線之上，長線趨勢偏多。")
    if not outlook_text["catalysts"]: outlook_text["catalysts"].append("**區間震盪**：目前缺乏明確攻擊訊號，等待量能放大。")

    # 風險
    if today['RSI'] > 75: outlook_text["risks"].append("**指標過熱**：RSI 指標過高，短線可能修正。")
    if fin_data['PE'] and float(fin_data['PE']) > 35: outlook_text["risks"].append("**估值偏高**：本益比高於市場平均，需留意修正風險。")
    if not outlook_text["risks"]: outlook_text["risks"].append("**系統風險**：留意大盤波動。")
    
    outlook_text["thesis"] = f"綜合分析，{fin_data['Name']} 評分為 **{score} 分**。基本面顯示{'獲利能力強勁' if adv_fin.get('ROE',0) > 10 else '獲利平穩'}。建議關注 **{verdict.split('(')[0]}**。"

    return {
        "id": stock_id, "name": fin_data['Name'], "price": today['Close'], "score": score,
        "verdict": verdict, "color": color, "reasons": reasons,
        "fin": fin_data, "chips": chips, "chip_status": chip_status,
        "insider": insider, 
        "histock_chip": histock_chip, # 改用 HiStock
        "adv_fin": adv_fin,
        "fin_source": fin_source,
        "today": today, "info": info, "zh_summary": zh_summary,
        "outlook": outlook_text
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
    
    with st.spinner("查詢中..."):
        data = generate_full_analysis(stock_code)
        
    if data:
        st.header(f"1. 執行摘要：{data['name']} ({stock_code})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("綜合信念評分", f"{data['score']} / 100")
        m2.metric("投資建議", data['verdict'].split(' ')[0])
        m3.metric("最新收盤價", f"{data['price']:.2f}")
        m4.caption(f"數據來源：HiStock + {data['fin_source']}")
        
        st.info(f"系統建議：**{data['verdict'].split('(')[0]}**。關鍵因素：**{data['reasons'][0] if data['reasons'] else '中性'}**。")

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏢 商業與基本面", "💰 財務與估值", "🏦 股權與籌碼", "📈 技術分析", "⚖️ 未來展望與戰略"])
        
        with tab1:
            st.subheader("業務背景")
            st.write(data['zh_summary'])
            st.markdown("---")
            st.caption(f"產業：{data['info'].get('sector', 'N/A')} > {data['info'].get('industry', 'N/A')}")
            
        with tab2:
            st.subheader("財務績效 (Financials)")
            st.caption(f"此頁數據來源：{data['fin_source']}")
            
            f1, f2, f3 = st.columns(3)
            pe = f"{data['fin']['PE']:.2f}" if data['fin']['PE'] else "N/A"
            pb = f"{data['fin']['PB']:.2f}" if data['fin']['PB'] else "N/A"
            yld = f"{data['fin']['Yield']:.2f}%" if data['fin']['Yield'] else "N/A"
            f1.metric("本益比 (P/E)", pe); f2.metric("股價淨值比 (P/B)", pb); f3.metric("殖利率", yld)

            st.divider()
            
            st.markdown("#### 📊 獲利能力與經營績效")
            gf = data['adv_fin']
            g1, g2, g3, g4 = st.columns(4)
            
            def fmt(v, suffix='%'): return f"{v:.2f}{suffix}" if v is not None else "N/A"
            
            g1.metric("毛利率", fmt(gf.get('GrossMargin')), help="越高越好")
            g2.metric("營業利益率", fmt(gf.get('OpMargin')))
            g3.metric("稅後淨利率", fmt(gf.get('NetMargin')))
            g4.metric("ROE (權益報酬)", fmt(gf.get('ROE')))
            
            st.write("")
            
            g5, g6, g7, g8 = st.columns(4)
            g5.metric("EPS (每股盈餘)", fmt(gf.get('EPS'), ' 元'))
            g6.metric("每股淨值 (BPS)", fmt(gf.get('BPS'), ' 元'))
            g7.metric("ROA (資產報酬)", fmt(gf.get('ROA')))
            g8.metric("參考來源", data['fin_source'])

        with tab3:
            st.subheader("所有權與交易動態")
            
            # ✅ HiStock 數據展示區
            st.markdown("#### 📊 集保分佈 (HiStock 嗨投資)")
            if data['histock_chip']:
                hc = data['histock_chip']
                g1, g2, g3 = st.columns(3)
                g1.metric("400張以上大戶", f"{hc['big_percent']}%", f"{hc['big_change']:.2f}%")
                g2.metric("股東人數", f"{hc['holders']} 人", f"{hc['holders_change']} 人", delta_color="inverse")
                g3.caption(f"統計日期：{hc['date']}")
                if hc['big_change'] > 0: st.success("🔥 籌碼集中 (大戶買)")
                elif hc['big_change'] < 0: st.error("⚠️ 籌碼鬆動 (大戶賣)")
            else:
                st.warning("⚠️ 暫時無法取得 HiStock 籌碼數據。")
            
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🏛️ 三大法人")
                if data['chips']: st.json(data['chips'])
            with c2:
                st.markdown("#### 👔 內部人持股")
                if data['insider']: st.metric("董監持股", f"{data['insider']}%")

        with tab4:
            st.subheader("技術分析")
            t1, t2, t3 = st.columns(3)
            t1.metric("RSI (14)", f"{data['today']['RSI']:.2f}")
            t2.metric("MACD", f"{data['today']['MACD'] - data['today']['Signal']:.2f}")
            t3.metric("月線乖離", f"{data['price'] - data['today']['MA20']:.2f}")

        with tab5:
            st.subheader("未來展望與戰略催化劑")
            st.markdown(f"**分析日期**：{datetime.date.today()}")
            st.markdown("#### 1. 戰略催化劑")
            for i in data['outlook']['catalysts']: st.markdown(f"- {i}")
            st.markdown("#### 2. 風險矩陣")
            for i in data['outlook']['risks']: st.markdown(f"- ⚠️ {i}")
            st.markdown("#### 3. 綜合投資論述")
            st.info(data['outlook']['thesis'])
            st.caption("*(免責聲明：本報告由 AI 自動生成，僅供參考)*")

    else:
        st.error(f"❌ 查無代碼 {stock_code}")
