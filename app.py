import streamlit as st
import json
import re
import os
from datetime import datetime
from prompts import get_stock_analysis_prompt

# 設定您的 API Key (建議放在 .env 檔案或是 Streamlit secrets)
# 這裡使用 OpenAI 為例，若用 Gemini 可改用 google.generativeai
import openai
# os.environ["OPENAI_API_KEY"] = "您的_API_KEY_放在這裡" 
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
    prompt = get_stock_analysis_prompt(company, ticker, current_date)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 或 gpt-4-turbo / gemini-pro
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
        if not os.getenv("OPENAI_API_KEY"):
            st.error("請先設定 API Key")
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
