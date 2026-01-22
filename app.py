import streamlit as st
import json
import re
import os
from datetime import datetime, timedelta
import google.generativeai as genai

# ==========================================
# 深度整合版 Prompt (融合您上傳的所有技術分析文件)
# ==========================================
# === 診斷代碼 (測試用，確認後可刪除) ===
import streamlit as st
try:
    test_key = st.secrets.get("GOOGLE_API_KEY")
    if not test_key:
        st.error("❌ 錯誤：Secrets 裡面找不到 'GOOGLE_API_KEY'。請檢查拼字。")
    else:
        st.success(f"✅ 成功：已偵測到 API Key (開頭為: {test_key[:5]}...)")
except FileNotFoundError:
    st.error("❌ 錯誤：找不到 secrets.toml 檔案。")
# ========================================def get_stock_analysis_prompt(company_name, ticker, current_date):
    next_year_date = (datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")

    base_prompt = f"""
[角色設定]
您是結合「華爾街機構操盤手」與「資深技術分析師」的 AI 投資顧問。
您的分析核心邏輯嚴格遵循使用者指定的以下實戰理論：

1. **道氏理論 (Dow Theory)**：以「高點更高、低點更高」確認主要趨勢方向。
2. **KD+MACD 共振戰法**：這是使用者強調的高勝率策略，必須尋找 KD 黃金交叉且 MACD 柱狀體翻紅的訊號。
3. **葛蘭碧八大法則 (Granville's Rules)**：利用均線 (MA) 的支撐與壓力來判斷買賣點。
4. **日本酒田戰法 (Candlestick Patterns)**：精確識別 K 線反轉訊號。
5. **產業生命週期**：針對科技/AI 股，判斷其處於「基礎建設」、「邊緣裝置」或「軟體應用」的哪一階段。

[研究對象]
公司：{company_name} ({ticker})
基準日：{current_date}

[分析任務與章節要求]
請根據台灣股市最新數據，撰寫一份 Markdown 格式的深度報告：

## 1. 執行摘要 (Executive Summary)
一句話總結目前的技術面與基本面狀態，並直接點出風險等級。

## 2. 產業週期與基本面 (Industry & Fundamentals)
* **AI 產業階段判斷**：依據財經M平方的邏輯，該公司目前是處於第一階段(基礎建設/雲端)、第二階段(Edge AI/手機筆電) 還是第三階段(軟體/應用)？
* **營收動能**：最近 3 個月營收年增率 (YoY) 趨勢。
* **估值位階**：本益比 (PE) 與 股價淨值比 (PB) 的歷史區間位置。

## 3. 籌碼面詳解 (Chip Analysis)
* **法人動向**：外資與投信近 5 日是連續買超、賣超還是調節？
* **大戶籌碼**：千張大戶持股比例是否增加？籌碼是否流向散戶？

## 4. 技術面深度戰法 (Technical Deep Dive) - *重點精華*
請嚴格依據以下邏輯進行分析：
* **趨勢定義 (道氏理論)**：目前是「多頭排列」(高過前高、低不破低) 還是空頭？
* **均線戰法 (葛蘭碧)**：
    * 股價是否回測均線(MA20/MA60)不破而上漲(買點)？
    * 股價是否乖離過大應注意拉回(賣點)？
* **指標雙重確認 (KD + MACD)**：
    * **KD 指標**：是否出現黃金交叉？(K值由下往上突破D值)
    * **MACD 指標**：柱狀體 (Histogram) 是否翻紅？
    * *關鍵判斷*：是否出現「KD 金叉 且 MACD 柱狀體向上」的**強勢共振訊號**？
* **K線型態 (酒田戰法)**：識別是否有「吞噬」、「錘頭」、「晨星」或「墓碑」等反轉型態。

## 5. 交易策略與風險 (Strategy & Risks)
* **進場規劃**：基於技術支撐位 (Support)，建議的佈局區間。
* **停損/停利**：基於壓力位 (Resistance) 或關鍵均線跌破的出場點。
* **風險因子**：供應鏈斷鏈、匯率波動或地緣政治風險。

## 6. 綜合評級 (Final Verdict)
給出明確的投資建議 (Buy/Hold/Sell) 與信念分數。

[結構化訊號輸出 - JSON]
**系統指令：** 請務必在回覆的「最後一段」，僅輸出以下 JSON 格式資料，供程式讀取 (不要包含 ```json 標籤)：
{{
  "ticker": "{ticker}",
  "analysis_date": "{current_date}",
  "recommendation": "Buy/Hold/Sell",
  "conviction_score": 85,
  "risk_level": "Low/Medium/High",
  "target_price_short_term": 0.0,
  "target_price_long_term": 0.0,
  "key_catalyst": "簡短描述(例如: KD+MACD共振金叉)",
  "chip_signal": "Bullish/Neutral/Bearish",
  "tech_signal": "Bullish/Neutral/Bearish",
  "trend_status": "Up/Down/Sideways"
}}
    """
    return base_prompt

# ==========================================
# 主程式邏輯 (Gemini API)
# ==========================================

# 從 Streamlit Secrets 讀取 Key (最安全的做法)
# 如果您在本地測試，可以暫時改為 api_key = "您的新Key"
api_key = st.secrets.get("GOOGLE_API_KEY")

if api_key:
    genai.configure(api_key=api_key)

def extract_json_from_text(text):
    """提取 JSON 的輔助函數"""
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return None
    except:
        return None

def analyze_stock(company, ticker):
    """執行分析"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = get_stock_analysis_prompt(company, ticker, current_date)
    
    try:
        # 使用 Gemini 1.5 Flash (速度快且免費額度高)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"AI 分析發生錯誤: {e}")
        return None

# ==========================================
# Streamlit UI 介面
# ==========================================
st.set_page_config(page_title="台股 AI 操盤手 (專業版)", layout="wide")

st.title("📈 台股 AI 深度投資分析 (KD+MACD 戰法)")
st.markdown("---")

# 側邊欄
with st.sidebar:
    st.header("參數設定")
    ticker_input = st.text_input("股票代號", value="2330")
    company_input = st.text_input("公司名稱", value="台積電")
    
    analyze_btn = st.button("🚀 啟動 AI 戰略分析")
    
    if not api_key:
        st.warning("⚠️ 未偵測到 API Key")
        st.info("請到 Streamlit Secrets 設定 GOOGLE_API_KEY")

# 主要邏輯
if analyze_btn:
    if not api_key:
        st.error("請先設定 API Key 才能開始分析！")
        st.stop()
        
    with st.spinner(f"正在運用道氏理論與 KD+MACD 模型分析 {company_input} ({ticker_input})..."):
        report_text = analyze_stock(company_input, ticker_input)
        
        if report_text:
            st.session_state['report'] = report_text
            st.session_state['json_data'] = extract_json_from_text(report_text)
            st.success("戰略分析完成！")

# 結果顯示
if 'report' in st.session_state:
    data = st.session_state.get('json_data')
    
    # 1. 儀表板區域
    if data:
        st.subheader("📊 戰略訊號儀表板")
        
        # 第一排：核心建議
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            rec = data.get('recommendation', 'N/A')
            color = "green" if rec == "Buy" else "red" if rec == "Sell" else "orange"
            st.markdown(f"**投資建議**")
            st.markdown(f"### :{color}[{rec}]")
        with c2:
            st.metric("信念分數 (0-100)", data.get('conviction_score', 0))
        with c3:
            st.metric("趨勢狀態", data.get('trend_status', 'N/A'))
        with c4:
            st.metric("短期目標價", data.get('target_price_short_term', 0))

        # 第二排：技術細節
        st.markdown("")
        c5, c6 = st.columns(2)
        with c5:
            st.info(f"🎯 **關鍵催化劑**: {data.get('key_catalyst')}")
        with c6:
            chip = data.get('chip_signal')
            tech = data.get('tech_signal')
            st.caption(f"籌碼面訊號: {chip} | 技術面訊號: {tech}")
            
        st.markdown("---")

    # 2. 完整報告區域
    st.subheader("📝 深度分析報告")
    st.markdown(st.session_state['report'])

