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

# 建立一個全局的 Session 來維持連線狀態 (對抗 Goodinfo)
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://goodinfo.tw/tw/StockDetail.asp"
})

# ==========================================
# 🕵️‍♂️ 數據獲取層
# ==========================================

def get_goodinfo_financials(stock_id):
    """
    [基本面] 強制爬取 Goodinfo 財務數據
    策略：使用 Session 模擬連續瀏覽，並增加欄位容錯率
    """
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "")
    url = f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={clean_id}"
    
    try:
        # 第一次請求可能需要拿 Cookie
        r = session.get(url, timeout=10)
        r.encoding = "utf-8"
        
        # 檢查是否被擋 (內容太少就是被擋)
        if len(r.text) < 1000:
            return None, "Goodinfo (Blocked)"
            
        dfs = pd.read_html(io.StringIO(r.text))
        data = {}
        
        # 遍歷表格找關鍵字
        for df in dfs:
            df_str = df.to_string()
            # 尋找包含獲利能力的表格
            if "毛利率" in df_str or "ROE" in df_str:
                # 轉成文字字典以便搜索
                text_map = {}
                for idx, row in df.iterrows():
                    for col in range(len(df.columns)-1):
                        k = str(row[col])
                        v = str(row[col+1])
                        text_map[k] = v
                
                def get_val(keywords):
                    for k, v in text_map.items():
                        if any(kw in k for kw in keywords):
                            # 清洗數據，只留數字和小數點
                            val = re.sub(r'[^\d.-]', '', v)
                            try:
                                return float(val)
                            except:
                                return None
                    return None

                # 嘗試抓取
                data['GrossMargin'] = get_val(['毛利率'])
                data['OpMargin'] = get_val(['營業利益率', '營益率'])
                data['NetMargin'] = get_val(['稅後淨利率', '淨利率'])
                data['ROE'] = get_val(['股東權益報酬率', 'ROE'])
                data['ROA'] = get_val(['資產報酬率', 'ROA'])
                data['EPS'] = get_val(['每股稅後盈餘', 'EPS', '每股盈餘'])
                data['BPS'] = get_val(['每股淨值'])
                
                # 只要抓到一個關鍵數據就算成功
                if data.get('GrossMargin') is not None:
                    return data, "Goodinfo"
                    
        return None, "Goodinfo (Parse Fail)"

    except Exception as e:
        print(f"Goodinfo Error: {e}")
        return None, "Goodinfo (Error)"

def get_histock_chips(stock_id):
    """
    [籌碼面] 從 HiStock (嗨投資) 抓取集保分佈
    修正：不依賴 pd.read_html，改用 BeautifulSoup 手術刀解析
    """
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "")
    url = f"https://histock.tw/stock/large.aspx?no={clean_id}"
    
    try:
        r = session.get(url, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # HiStock 的表格通常有特定的 class 或結構
        # 我們直接找包含 "400張" 的那個表格
        tables = soup.find_all('table')
        target_table = None
        
        for t in tables:
            if "400張" in t.text and "股東人數" in t.text:
                target_table = t
                break
        
        if target_table:
            # 找到表格後，抓取所有的 tr (列)
            rows = target_table.find_all('tr')
            # 排除標題列，取資料列 (通常第二列開始是最新一週)
            # rows[0] 是標題, rows[1] 是最新週, rows[2] 是上週
            if len(rows) >= 3:
                row_now = rows[1].find_all('td')
                row_prev = rows[2].find_all('td')
                
                # HiStock 欄位順序可能會變，但通常是：
                # 週別 | 收盤價 | ... | 400張比例 | ... | 股東人數 | ...
                
                # 我們用「欄位標題」來定位 index
                headers = [th.text.strip() for th in rows[0].find_all('th')]
                if not headers: # 有時候是 td
                    headers = [td.text.strip() for td in rows[0].find_all('td')]
                
                idx_big = -1
                idx_holders = -1
                idx_date = 0
                
                for i, h in enumerate(headers):
                    if "400張" in h and "%" in h: idx_big = i
                    if "人數" in h: idx_holders = i
                    if "期" in h or "周" in h or "日" in h: idx_date = i
                
                if idx_big != -1 and idx_holders != -1:
                    # 抓數據
                    curr_big = float(row_now[idx_big].text.replace('%', '').strip())
                    prev_big = float(row_prev[idx_big].text.replace('%', '').strip())
                    
                    curr_hold = int(row_now[idx_holders].text.replace(',', '').strip())
                    prev_hold = int(row_prev[idx_holders].text.replace(',', '').strip())
                    
                    date_str = row_now[idx_date].text.strip()
                    
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
    """Yahoo 基礎估值數據"""
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
# 📝 報告生成引擎 (v10.0 Final)
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
    
    # ✅ 強制抓取 Goodinfo (基本面)
    adv_fin, fin_source_status = get_goodinfo_financials(stock_id)
    
    # ✅ 強制抓取 HiStock (籌碼面)
    histock_chip = get_histock_chips(stock_id)
    
    # 若 Goodinfo 徹底失敗，至少給空字典以免報錯
    if not adv_fin: adv_fin = {}
    
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
    
    # 基本面 (Goodinfo)
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
    
    thesis_fin = '獲利能力強勁' if adv_fin.get('ROE',0) > 10 else '獲利平穩'
    if not adv_fin: thesis_fin = "財務數據待確認"
    
    outlook_text["thesis"] = f"綜合分析，{fin_data['Name']} 評分為 **{score} 分**。基本面顯示{thesis_fin}。建議關注 **{verdict.split('(')[0]}**。"

    return {
        "id": stock_id, "name": fin_data['Name'], "price": today['Close'], "score": score,
        "verdict": verdict, "color": color, "reasons": reasons,
        "fin": fin_data, "chips": chips, "chip_status": chip_status,
        "insider": insider, 
        "histock_chip": histock_chip, 
        "adv_fin": adv_fin,
        "fin_source_status": fin_source_status,
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
        m4.caption(f"來源狀態：{data['fin_source_status']}")
        
        st.info(f"系統建議：**{data['verdict'].split('(')[0]}**。關鍵因素：**{data['reasons'][0] if data['reasons'] else '中性'}**。")

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏢 商業與基本面", "💰 財務與估值", "🏦 股權與籌碼", "📈 技術分析", "⚖️ 未來展望與戰略"])
        
        with tab1:
            st.subheader("業務背景")
            st.write(data['zh_summary'])
            st.markdown("---")
            st.caption(f"產業：{data['info'].get('sector', 'N/A')} > {data['info'].get('industry', 'N/A')}")
            
        with tab2:
            st.subheader("財務績效 (Financials)")
            
            f1, f2, f3 = st.columns(3)
            pe = f"{data['fin']['PE']:.2f}" if data['fin']['PE'] else "N/A"
            pb = f"{data['fin']['PB']:.2f}" if data['fin']['PB'] else "N/A"
            yld = f"{data['fin']['Yield']:.2f}%" if data['fin']['Yield'] else "N/A"
            f1.metric("本益比 (P/E)", pe); f2.metric("股價淨值比 (P/B)", pb); f3.metric("殖利率", yld)

            st.divider()
            
            st.markdown(f"#### 📊 獲利能力與經營績效 (Goodinfo)")
            if data['adv_fin']:
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
                g8.caption(f"數據來源：{data['fin_source_status']}")
            else:
                st.warning(f"⚠️ 無法取得 Goodinfo 數據，狀態：{data['fin_source_status']}")

        with tab3:
            st.subheader("所有權與交易動態")
            
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
                st.warning("⚠️ 嗨投資爬蟲未抓取到表格，可能網頁結構改變。")
            
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
