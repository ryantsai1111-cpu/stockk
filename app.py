import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import datetime
import io
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
# 🕵️‍♂️ 數據獲取層 (TWSE 官方 API + yfinance)
# ==========================================

@st.cache_data(ttl=3600) # 快取 1 小時，避免重複呼叫
def get_twse_data_all():
    """
    一次抓取 TWSE 所有股票的最新數據 (官方 API)
    包含：本益比、殖利率、三大法人買賣超
    """
    data_store = {}
    
    try:
        # 1. 抓取 [個股日本益比、殖利率及股價淨值比]
        # API: https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL
        url_fin = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        r_fin = requests.get(url_fin)
        df_fin = pd.DataFrame(r_fin.json())
        
        # 整理欄位 (Code, Name, PEratio, DividendYield, PBratio)
        # 建立字典索引，方便後續快速查找
        for _, row in df_fin.iterrows():
            code = row['Code']
            data_store[code] = {
                "PE": row.get('PEratio', 'N/A'),
                "Yield": row.get('DividendYield', 'N/A'),
                "PB": row.get('PBratio', 'N/A'),
                "Name": row.get('Name', code)
            }

        # 2. 抓取 [三大法人買賣超日報]
        # API: https://openapi.twse.com.tw/v1/fund/T86_ALL
        url_chip = "https://openapi.twse.com.tw/v1/fund/T86_ALL"
        r_chip = requests.get(url_chip)
        df_chip = pd.DataFrame(r_chip.json())
        
        # 整理三大法人數據
        for _, row in df_chip.iterrows():
            code = row['Code']
            if code in data_store:
                # 單位原本是「股」，除以 1000 轉成「張」
                def to_zhang(val):
                    try: return int(val.replace(',', '')) // 1000
                    except: return 0
                
                data_store[code]['Chips'] = {
                    "Foreign": to_zhang(row.get('ForeignInvestorNetBuySell', 0)), # 外資
                    "Trust": to_zhang(row.get('InvestmentTrustNetBuySell', 0)),   # 投信
                    "Dealer": to_zhang(row.get('DealerNetBuySell', 0))            # 自營商
                }
    except Exception as e:
        print(f"TWSE API Error: {e}")
        
    return data_store

def get_stock_data(stock_id):
    """整合 yfinance 歷史數據 + TWSE 官方即時數據"""
    
    # 1. 取得 TWSE 官方全市場數據 (快取)
    twse_data_all = get_twse_data_all()
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "")
    
    # 從大表中撈出這檔股票
    twse_stock = twse_data_all.get(clean_id)
    
    # 2. yfinance 抓歷史股價 (畫圖用)
    stock = yf.Ticker(stock_id)
    df = stock.history(period="1y")
    
    if df.empty: return None
    
    # 計算技術指標
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
    
    info = stock.info
    zh_summary = translate_to_chinese(info.get('longBusinessSummary', ''))
    
    return {
        "id": stock_id,
        "price": df.iloc[-1]['Close'],
        "history": df,
        "twse": twse_stock, # 官方數據包
        "info": info,
        "summary": zh_summary
    }

# ==========================================
# 📝 報告生成引擎 (Official API Version)
# ==========================================
def generate_report(stock_id):
    data = get_stock_data(stock_id)
    if not data: return None
    
    # 解包數據
    twse = data['twse']
    today = data['history'].iloc[-1]
    chips = twse.get('Chips', {'Foreign': 0, 'Trust': 0, 'Dealer': 0}) if twse else None
    
    # --- 評分系統 ---
    score = 50
    reasons = []
    
    # 技術面
    if today['Close'] > today['MA20']: score += 10; reasons.append("站上月線，短多格局")
    else: score -= 10; reasons.append("跌破月線，短線整理")
    if today['Close'] > today['MA60']: score += 10; reasons.append("站穩季線，長線看好")
    else: score -= 10
    if today['RSI'] < 30: score += 5; reasons.append("RSI 超賣，醞釀反彈")
    
    # 籌碼面 (TWSE 官方)
    chip_status = "中性觀望"
    if chips:
        f, t = chips['Foreign'], chips['Trust']
        if f > 0 and t > 0: score += 20; chip_status = "土洋合一 (法人齊買)"; reasons.append("外資投信同步買超")
        elif f < 0 and t < 0: score -= 20; chip_status = "法人棄守 (雙重賣壓)"; reasons.append("外資投信同步調節")
        elif t > 0: score += 10; chip_status = "投信認養"; reasons.append("投信買超護盤")
        elif f > 0: score += 5; chip_status = "外資買進"
        
    # 基本面 (TWSE 官方)
    if twse and twse['Yield'] != 'N/A' and float(twse['Yield']) > 4:
        score += 5; reasons.append(f"高殖利率 ({twse['Yield']}%)")
    if twse and twse['PE'] != 'N/A' and float(twse['PE']) < 15:
        score += 5; reasons.append(f"本益比低 ({twse['PE']})")

    score = max(0, min(100, score))
    
    if score >= 75: verdict = "強力買進"; color = "green"
    elif score >= 55: verdict = "持有/觀望"; color = "orange"
    else: verdict = "賣出/避開"; color = "red"
    
    # --- 未來展望 (AI 邏輯) ---
    outlook = {"catalysts": [], "risks": [], "thesis": ""}
    
    # 催化劑
    if chips and chips['Trust'] > 0: outlook['catalysts'].append("**內資作帳**：投信近期站在買方，季底作帳行情可期。")
    if today['Close'] > today['MA60']: outlook['catalysts'].append("**均線支撐**：股價位於季線之上，下方支撐強勁。")
    if twse and twse['Yield'] != 'N/A' and float(twse['Yield']) > 5: outlook['catalysts'].append("**存股價值**：高殖利率提供下檔保護。")
    if not outlook['catalysts']: outlook['catalysts'].append("**區間整理**：等待量能放大突破。")
    
    # 風險
    if today['RSI'] > 75: outlook['risks'].append("**技術過熱**：RSI 指標進入超買區，短線隨時可能回檔。")
    if chips and chips['Foreign'] < 0: outlook['risks'].append("**外資提款**：外資近期賣超，籌碼面有鬆動疑慮。")
    
    outlook['thesis'] = f"綜合 TWSE 官方數據分析，{twse['Name'] if twse else stock_id} 目前評分為 **{score} 分**。籌碼面呈現 **{chip_status}** 態勢。建議投資人採取 **{verdict}** 策略，並以月線 {today['MA20']:.2f} 作為防守點。"

    return {
        "id": stock_id, "name": twse.get('Name', stock_id) if twse else stock_id,
        "price": today['Close'], "score": score, "verdict": verdict, "color": color,
        "twse": twse, "chips": chips, "chip_status": chip_status,
        "history": data['history'], "today": today, "summary": data['summary'],
        "outlook": outlook
    }

# ==========================================
# 🖥️ UI 介面
# ==========================================
st.title("帥哥城 AI 投顧")
st.markdown("### 🚀 機構級投資分析報告書 (TWSE 官方數據版)")

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
    
    with st.spinner("正在連線證交所 (TWSE Open API)..."):
        data = generate_report(stock_code)
        
    if data:
        st.header(f"1. 執行摘要：{data['name']} ({stock_code})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("綜合信念評分", f"{data['score']} / 100")
        m2.metric("投資建議", data['verdict'])
        m3.metric("最新收盤價", f"{data['price']:.2f}")
        m4.caption("數據來源：TWSE 官方 API")
        
        st.info(f"系統觀點：目前籌碼呈現 **{data['chip_status']}**。{data['outlook']['thesis']}")

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏢 商業背景", "💰 財務估值", "🏦 法人籌碼", "📈 技術分析", "⚖️ 未來展望"])
        
        with tab1:
            st.subheader("業務背景")
            st.write(data['summary'])
            st.markdown("---")
            st.caption(f"產業分類：{data['twse'].get('Industry', '一般產業') if data['twse'] else 'N/A'}")
            
        with tab2:
            st.subheader("財務績效 (TWSE 官方數據)")
            if data['twse']:
                f1, f2, f3 = st.columns(3)
                f1.metric("本益比 (P/E)", data['twse']['PE'])
                f2.metric("股價淨值比 (P/B)", data['twse']['PB'])
                f3.metric("殖利率 (Yield)", f"{data['twse']['Yield']}%")
                st.caption("註：數據即時來自證交所 Open API，準確度最高。")
            else:
                st.warning("查無官方財務數據")

        with tab3:
            st.subheader("三大法人籌碼 (TWSE T86)")
            if data['chips']:
                c1, c2, c3 = st.columns(3)
                c1.metric("外資買賣超", f"{data['chips']['Foreign']} 張", delta_color="normal")
                c2.metric("投信買賣超", f"{data['chips']['Trust']} 張", delta_color="normal")
                c3.metric("自營商買賣超", f"{data['chips']['Dealer']} 張", delta_color="normal")
                
                if data['chips']['Foreign'] > 0 and data['chips']['Trust'] > 0:
                    st.success("🔥 土洋合一：外資與投信同步站在買方！")
                elif data['chips']['Foreign'] < 0 and data['chips']['Trust'] < 0:
                    st.error("❄️ 法人棄守：外資與投信同步賣超提款。")
            else:
                st.warning("今日尚無法人交易數據 (可能為盤中或假日)")
            
            st.info("💡 提示：此 API 僅提供「三大法人」數據，無「集保股權分散」資料。")

        with tab4:
            st.subheader("技術分析")
            t1, t2, t3 = st.columns(3)
            t1.metric("RSI (14)", f"{data['today']['RSI']:.2f}")
            t2.metric("MACD", f"{data['today']['MACD'] - data['today']['Signal']:.2f}")
            t3.metric("月線乖離", f"{data['price'] - data['today']['MA20']:.2f}")
            
            # 簡單畫個圖
            st.line_chart(data['history']['Close'])

        with tab5:
            st.subheader("未來展望與戰略 (AI)")
            st.markdown(f"**分析日期**：{datetime.date.today()}")
            st.markdown("#### 1. 戰略催化劑")
            for i in data['outlook']['catalysts']: st.markdown(f"- {i}")
            st.markdown("#### 2. 風險矩陣")
            for i in data['outlook']['risks']: st.markdown(f"- ⚠️ {i}")
            st.markdown("#### 3. 綜合投資論述")
            st.info(data['outlook']['thesis'])

    else:
        st.error(f"❌ 查無代碼 {stock_code}，請確認是否為上市股票。")
