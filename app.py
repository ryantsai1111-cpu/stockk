import streamlit as st
import json
import re
import os
from datetime import datetime, timedelta
import google.generativeai as genai

# ==========================================
# 核心大腦：融合您提供的所有技術分析文件
# ==========================================
def get_stock_analysis_prompt(company_name, ticker, current_date):
    next_year_date = (datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")

    base_prompt = f"""
[角色設定]
您是結合「華爾街機構操盤手」與「技術分析大師」的 AI 投資顧問。
您的分析必須嚴格遵守以下使用者指定的實戰理論，不能僅給出模稜兩可的建議：

1. **道氏理論 (Dow Theory)**：
   - 趨勢確認：必須檢查是否符合「高點更高 (Higher Highs)、低點更高 (Higher Lows)」的多頭定義。
   - 相互驗證：確認大盤與個股走勢是否背離。

2. **最強指標共振 (KD + MACD)**:
   - **這是本策略的核心買點**：尋找 KD 指標黃金交叉，**同時** MACD 柱狀體 (Histogram) 翻紅或向上擴大的時刻。
   - 根據文件，這種雙重確認能將勝率提高至 80% 以上，請特別標註此訊號。

3. **葛蘭碧八大法則 (Granville's Rules)**:
   - 利用 MA20/MA60 判斷：
     - 買點：均線向上且股價回測不破、或乖離過大後的反彈。
     - 賣點：均線走平下彎且股價跌破、或乖離過大後的拉回。

4. **K線與型態學 (酒田戰法)**:
   - 識別關鍵變盤訊號：如「吞噬 (Engulfing)」、「錘頭 (Hammer)」、「晨星/暮星」、「墓碑線」。

5. **布林通道與乖離率**:
   - 判斷股價是否沿著上軌 (Band Walk) 強勢攻擊，或是觸及下軌超賣。

6. **AI 產業生命週期**:
   - 針對科技股，判斷目前處於：
     - 第一階段：基礎建設 (Cloud/Server)
     - 第二階段：邊緣裝置 (Edge AI/PC/Phone) - *目前的關注重點*
     - 第三階段：軟體應用 (App/Services)

[研究對象]
公司：{company_name} ({ticker})
基準日：{current_date}

[輸出報告格式]
請撰寫一份 Markdown 專業報告，包含：

## 1. 操盤手快訊 (Executive Summary)
- 目前的多空判斷 (Bullish/Bearish/Neutral)。
- 最強烈的技術訊號是什麼？(例如：KD+MACD 共振金叉)

## 2. 產業地位與週期 (Based on AI 2025 Outlook)
- 該公司位於 AI 發展的哪一個階段？
- 營收動能 YoY 的解讀。

## 3. 籌碼博弈 (Chip Analysis)
- **法人動向**：外資與投信近期的連續買賣超行為 (投信作帳/外資提款)。
- **大戶 vs 散戶**：籌碼是集中還是發散？

## 4. 技術面深度戰略 (Technical Strategy) - *最重要章節*
*請依照道氏理論與葛蘭碧法則進行多維度掃描：*
- **趨勢結構**：多頭排列 / 空頭排列 / 盤整。
- **指標共振檢查**：
   - KD 狀態：(數值/交叉方向)
   - MACD 狀態：(柱狀體顏色/DIF與DEA位置)
   - **結論**：是否出現「KD+MACD」共振買點？
- **K線解讀**：近期是否有反轉 K 線型態？
- **支撐與壓力**：基於布林通道或均線的關鍵價位。

## 5. 交易計畫 (Trading Plan)
- **進場區間**：建議的買入價格帶 (基於支撐位)。
- **停損設定**：跌破哪個關鍵價位 (如 MA60) 必須離場？
- **目標價位**：短期與長期目標 ({current_date} ~ {next_year_date})。

[結構化訊號 - JSON]
**系統強制要求：** 請在報告的**最後一段**，單獨輸出以下 JSON 格式資料 (供程式讀取儀表板使用)：
{{
  "ticker": "{ticker}",
  "recommendation": "Buy/Hold/Sell",
  "conviction_score": 85,
  "trend_status": "Up/Down/Sideways",
  "chip_signal": "Bullish/Neutral/Bearish",
  "tech_signal": "Bullish/Neutral/Bearish",
  "key_catalyst": "簡短描述(如:KD+MACD共振)",
  "target_price_short_term": 0.0
}}
    """
    return base_prompt

# ==========================================
# 主程式邏輯 (Gemini API)
# ==========================================

# 讀取 API Key (優先從 Secrets 讀取)
api_key = st.secrets.get("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def extract_json_from_text(text):
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except:
        pass
    return None

def analyze_stock(company, ticker):
    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = get_stock_analysis_prompt(company, ticker, current_date)
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"連線錯誤：{e}")
        return None

# ==========================================
# UI 介面
# ==========================================
st.set_page_config(page_title="專業操盤手 AI", layout="wide")
st.title("📈 專業操盤手 AI (道氏+葛蘭碧+指標共振版)")

with st.sidebar:
    st.header("股票設定")
    ticker_input = st.text_input("代號", value="2330")
    company_input = st.text_input("名稱", value="台積電")
    run_btn = st.button("🚀 執行戰略分析")
    
    if not api_key:
        st.error("⚠️ 未設定 API Key")
        st.info("請至 Secrets 設定 GOOGLE_API_KEY")

if run_btn and api_key:
    with st.spinner(f"正在運用 KD+MACD 與道氏理論掃描 {company_input}..."):
        report = analyze_stock(company_input, ticker_input)
        if report:
            st.session_state['report'] = report
            st.session_state['data'] = extract_json_from_text(report)

if 'report' in st.session_state:
    data = st.session_state.get('data')
    if data:
        # 儀表板
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("投資建議", data.get('recommendation'), data.get('conviction_score'))
        c2.metric("趨勢狀態", data.get('trend_status'))
        c3.metric("籌碼/技術", f"{data.get('chip_signal')} / {data.get('tech_signal')}")
        c4.metric("目標價", data.get('target_price_short_term'))
        st.info(f"🔑 **關鍵訊號**：{data.get('key_catalyst')}")
        st.markdown("---")
    
    st.markdown(st.session_state['report'])
