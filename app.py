import streamlit as st
import json
import re
import os
from datetime import datetime, timedelta
import openai

# ==========================================
# 這是原本 prompts.py 的內容，直接放在這裡就不用 import 了
# ==========================================
def get_stock_analysis_prompt(company_name, ticker, current_date):
    # 計算明年日期 (用於預測區間)
    next_year_date = (datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")

    base_prompt = f"""
[角色和背景]
您是專門研究台灣上市與上櫃公司的專家級高級市場分析師。您的使命是為私人投資者提供深度、多維度、前沿的投資情報報告。

[研究對象]
公司名稱：{company_name}
股票代號：{ticker}
分析基準日：{current_date}

[研究範圍與來源]
請整合以下資訊來源：
1. 官方數據：台灣證券交易所(TWSE)、櫃買中心(TPEx)、公開資訊觀測站(MOPS)。
2. 籌碼數據：三大法人(外資/投信/自營商)買賣超、融資融券變化、大戶持股比例。
3. 非傳統數據：社群情緒(PTT/Mobile01)、行業論壇、法說會內容。

[報告章節要求]
請完成一份結構完整的報告，Markdown 格式，包含：

1. **執行摘要**：關鍵見解與風險。
2. **業務背景**：核心模式、積壓訂單(Backlog)狀況。
3. **財務與股利**：EPS成長率、本益比位階、現金股利殖利率、歷史填息能力分析。
4. **籌碼面與主力動向 (重點)**：
   - 三大法人動向分析 (是否有投信作帳或外資連續買超)。
   - 籌碼集中度 (大戶 vs 散戶持股變化)。
5. **技術分析與交易時機**：
   - 均線排列 (MA20/60/240)。
   - 關鍵支撐與壓力位。
   - 技術指標 (RSI, KD, MACD) 狀態。
6. **供應鏈與競爭**：客戶集中度風險、庫存循環狀態(DOI)。
7. **風險評估**：地緣政治、匯率、資安風險。
8. **未來展望**：營收預測與催化劑。
9. **私人投資者最終評估**：
   - 給出 {current_date} 至 {next_year_date} 的股價預測區間。
   - 明確建議：買入(Buy) / 持有(Hold) / 賣出(Sell)。

[結構化訊號輸出 - JSON]
**非常重要：** 在報告的最末端，請務必提供以下單純的 JSON 區塊 (不要包含 Markdown 代碼標記如 ```json)，供程式解析使用：

{{
  "ticker": "{ticker}",
  "analysis_date": "{current_date}",
  "recommendation": "Buy/Hold/Sell",
  "conviction_score": 85, 
  "risk_level": "Low/Medium/High",
  "target_price_short_term": 0.0,
  "target_price_long_term": 0.0,
  "key_catalyst": "簡短描述關鍵催化劑",
  "chip_signal": "Bullish/Neutral/Bearish",
  "tech_signal": "Bullish/Neutral/Bearish",
  "summary_one_line": "一句話總結"
}}
    """
    return base_prompt

# ==========================================
# 主程式邏輯
# ==========================================

# 設定 API Key
# 注意：在 Streamlit Cloud 上，建議在 "App Settings" -> "Secrets" 裡設定 OPENAI_API_KEY
client = openai.Client(api_key=os.getenv("OPENAI_API_KEY"))

def extract_json_from_text(text):
    """
    從 AI 的長篇回覆中，使用正則表達式精準提取 JSON 區塊
    """
    try:
        # 嘗試尋找 JSON 格式的字串 (包含在大括號內的內容)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            return None
    except json.JSONDecodeError:
        return None

def analyze_stock(company, ticker):
    """
    呼叫 AI 進行分析
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 直接呼叫同一個檔案裡的函數
    prompt = get_stock_analysis_prompt(company, ticker, current_date)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 確保您有 GPT-4 權限，否則改用 gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "You are a professional financial analyst specialized in the Taiwan Stock Market."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"AI 分析發生錯誤: {e}")
        return None

# --- Streamlit UI 佈局 ---
st.set_page_config(page_title="台股 AI 智能分析師", layout="wide")

st.title("📈 台股 AI 深度投資分析報告")
st.markdown("---")

# 側邊欄輸入
with st.sidebar:
    st.header("輸入參數")
    ticker_input = st.text_input("股票代號 (Ticker)", value="2330")
    company_input = st.text_input("公司名稱", value="台積電")
    
    if st.button("🚀 開始 AI 分析"):
        # 檢查是否有 API Key
        if not client.api_key:
            st.error("⚠️ 未偵測到 API Key。請在 Streamlit Cloud 的 Secrets 設定中加入 OPENAI_API_KEY。")
        else:
            with st.spinner(f"正在深入分析 {company_input} ({ticker_input}) 的籌碼、財報與技術面..."):
                report_text = analyze_stock(company_input, ticker_input)
                
                if report_text:
                    st.session_state['report'] = report_text
                    st.session_state['json_data'] = extract_json_from_text(report_text)
                    st.success("分析完成！")

# 顯示結果區
if 'report' in st.session_state:
    # 1. 儀表板區域 (Dashboard)
    data = st.session_state.get('json_data')
    
    if data:
        st.subheader("📊 投資訊號儀表板")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            rec = data.get('recommendation', 'N/A')
            # 簡單的顏色判斷
            color = "green" if rec == "Buy" else "red" if rec == "Sell" else "orange"
            st.markdown(f"**投資建議**")
            st.markdown(f":{color}[{rec}]")
            
        with col2:
            st.metric("信念分數 (0-100)", data.get('conviction_score', 0))
            
        with col3:
            st.metric("目標價 (短期)", data.get('target_price_short_term', 0))
            
        with col4:
            st.markdown("**訊號總結**")
            st.caption(f"籌碼面: {data.get('chip_signal')}")
            st.caption(f"技術面: {data.get('tech_signal')}")
        
        st.info(f"💡 **關鍵催化劑**: {data.get('key_catalyst')}")
        st.markdown("---")

    # 2. 完整報告區域
    st.subheader("📝 完整分析報告")
    st.markdown(st.session_state['report'])
