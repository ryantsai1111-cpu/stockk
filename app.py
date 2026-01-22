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
您的分析必須嚴格遵守以下使用者指定的實戰理論，這不是普通建議，而是戰略部署：

1. **道氏理論 (Dow Theory)**：
   - 趨勢確認：必須檢查是否符合「高點更高 (Higher Highs)、低點更高 (Higher Lows)」的多頭定義。
   - 若高點不再創新高且跌破前低，必須標示為空頭反轉訊號。

2. **最強指標共振 (KD + MACD)**：
   - **核心買點**：尋找 KD 指標(9,3,3)黃金交叉，**同時** MACD 柱狀體 (Histogram) 翻紅或向上擴大的時刻。
   - **核心賣點**：KD 死亡交叉且 MACD 綠柱擴大。
   - 請特別標註是否出現「共振 (Resonance)」現象，這能大幅提高勝率。

3. **葛蘭碧八大法則 (Granville's Rules)**：
   - 利用 MA20 (月線) 與 MA60 (季線) 判斷：
     - 買點：均線翻揚且股價回測不破。
     - 賣點：均線下彎且股價反彈不過。

4. **K線與型態學 (酒田戰法)**：
   - 識別關鍵變盤訊號：如「吞噬 (Engulfing)」、「錘頭 (Hammer)」、「晨星/暮星」。

5. **AI 產業生命週期 (AI Outlook)**：
   - 針對科技股，判斷目前處於：
     - 第一階段：基礎建設 (Cloud/Server/ASIC)
     - 第二階段：邊緣裝置 (Edge AI/PC/Phone) - *目前的資金輪動焦點*
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
- **均線與乖離**：目前股價相對於 MA20/MA60 的位置。

## 5. 交易計畫 (Trading Plan)
- **進場區間**：建議的買入價格帶 (基於支撐位)。
- **停損設定**：跌破哪個關鍵價位 (如 MA60) 必須離場？
- **目標價位**：短期與長期目標 ({current_date} ~ {next_year_date})。

[結構化訊號 - JSON]
**系統強制要求：** 請在報告的**最後一段**，單獨輸出以下 JSON 格式資料 (供程式讀取儀表板使用，不要包含 ```json 標籤)：
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

# 設定 Google Gemini
if api_key:
    genai.configure(api_key=api_key)

def extract_json_from_text(text):
    """從回應中提取 JSON 數據，增加容錯率"""
    try:
        # 嘗試抓取 { ... } 之間的內容
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
    except Exception:
        return None
    return None

def analyze_stock(company, ticker):
    """呼叫 AI 進行分析"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = get_stock_analysis_prompt(company, ticker, current_date)
    
    try:
        # 使用 Gemini 1.5 Flash 模型 (快速且免費額度高)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# ==========================================
# UI 介面設計
# ==========================================
st.set_page_config(page_title="專業操盤手 AI", layout="wide", page_icon="📈")

st.title("📈 專業操盤手 AI (道氏+葛蘭碧+指標共振版)")
st.markdown("---")

# 側邊欄：設定與狀態檢查
with st.sidebar:
    st.header("1. 系統狀態")
    if api_key:
        if api_key.startswith("AIza"):
            st.success("✅ API Key 格式正確 (Google)")
        elif api_key.startswith("sk-"):
            st.error("❌ 偵測到 OpenAI Key，請更換為 Google Gemini Key")
        else:
            st.warning("⚠️ API Key 格式可能不正確")
    else:
        st.error("❌ 未偵測到 API Key")
        st.info("請至 Secrets 設定 `GOOGLE_API_KEY`")

    st.header("2. 股票設定")
    ticker_input = st.text_input("股票代號", value="2330")
    company_input = st.text_input("公司名稱", value="台積電")
    
    run_btn = st.button("🚀 執行戰略分析", type="primary")
    st.markdown("---")
    st.caption("策略核心：\n1. 道氏理論趨勢\n2. KD+MACD 共振\n3. AI 產業週期")

# 主要執行邏輯
if run_btn:
    if not api_key:
        st.error("⛔ 無法執行：請先設定 API Key。")
        st.stop()
        
    if not api_key.startswith("AIza"):
        st.error("⛔ 無法執行：Key 格式錯誤，這不是 Gemini 的 Key。")
        st.stop()

    with st.spinner(f"正在運用 KD+MACD 與道氏理論掃描 {company_input} ({ticker_input})..."):
        report = analyze_stock(company_input, ticker_input)
        
        # 錯誤處理
        if report and report.startswith("Error:"):
            st.error(f"連線失敗：{report}")
            st.write("建議：請檢查 Key 是否已被刪除，或嘗試 Reboot App。")
        elif report:
            st.session_state['report'] = report
            st.session_state['data'] = extract_json_from_text(report)
            st.balloons()

# 報告顯示區域
if 'report' in st.session_state:
    data = st.session_state.get('data')
    
    # 1. 戰情儀表板
    if data:
        st.subheader("📊 戰略訊號儀表板")
        c1, c2, c3, c4 = st.columns(4)
        
        # 投資建議顏色
        rec = data.get('recommendation', 'Hold')
        rec_color = "green" if rec == "Buy" else "red" if rec == "Sell" else "orange"
        
        with c1:
            st.markdown(f"**投資建議**")
            st.markdown(f"### :{rec_color}[{rec}]")
        with c2:
            st.metric("趨勢狀態", data.get('trend_status', 'N/A'))
        with c3:
            st.metric("籌碼/技術", f"{data.get('chip_signal')} / {data.get('tech_signal')}")
        with c4:
            st.metric("目標價", data.get('target_price_short_term', 0))
            
        st.info(f"🔑 **關鍵催化劑**：{data.get('key_catalyst', '分析中...')}")
        st.markdown("---")
    
    # 2. 完整文字報告
    st.subheader("📝 深度分析報告")
    st.markdown(st.session_state['report'])
