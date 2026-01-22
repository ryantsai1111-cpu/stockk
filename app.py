import streamlit as st
import os

st.title("🔧 API 連線診斷中心")

# 1. 檢查套件是否安裝
st.subheader("1. 檢查套件安裝")
try:
    import google.generativeai as genai
    st.success("✅ `google-generativeai` 套件已安裝！")
    has_lib = True
except ImportError:
    st.error("❌ 嚴重錯誤：找不到 `google-generativeai` 套件。")
    st.info("💡 解決方法：請去 GitHub 的 `requirements.txt` 檔案，加入一行 `google-generativeai`。")
    has_lib = False

# 2. 檢查 API Key 設定
st.subheader("2. 檢查 API Key 設定")
api_key = st.secrets.get("GOOGLE_API_KEY")

if api_key:
    # 遮蔽 Key 的中間部分，只顯示頭尾，確認是不是新的一把
    masked_key = f"{api_key[:5]}...{api_key[-4:]}"
    st.success(f"✅ 成功讀取到 Key：{masked_key}")
    
    # 檢查是否還是舊的 OpenAI Key (常見錯誤)
    if api_key.startswith("sk-"):
        st.warning("⚠️ 警告：這看起來像是 OpenAI 的 Key (sk-開頭)，但我們現在用的是 Google Gemini (應該是 AIza 開頭)。")
    elif api_key.startswith("AIza"):
        st.info("ℹ️ 格式正確：這是 Google 的 Key。")
else:
    st.error("❌ 錯誤：抓不到 `GOOGLE_API_KEY`。")
    st.markdown("""
    **請檢查 Streamlit Secrets 設定：**
    1. 點擊右下角 **Manage app** > **Settings** > **Secrets**
    2. 確認內容是否為：
    ```toml
    GOOGLE_API_KEY = "AIzaSy..."
    ```
    *(注意：變數名稱必須完全一樣，不能是 OPENAI_API_KEY)*
    """)

# 3. 實際連線測試
st.subheader("3. 實際連線測試")
if st.button("🚀 測試 AI 回應"):
    if has_lib and api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content("哈囉！如果你活著請回答我「連線成功」。")
            st.balloons()
            st.success(f"🎉 測試成功！AI 回應：{response.text}")
            st.markdown("---")
            st.write("👉 **現在您可以把原本的股票分析代碼貼回去了！**")
        except Exception as e:
            st.error(f"❌ 連線失敗，錯誤訊息：{e}")
            st.write("這通常代表 Key 是錯的，或者被 Google 刪除了。請去 Google AI Studio 重新產生一把。")
    else:
        st.error("無法測試：請先修復上述紅色的錯誤。")
