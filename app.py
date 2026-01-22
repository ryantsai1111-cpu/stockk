import streamlit as st
import google.generativeai as genai

st.title("🔍 API Key 診斷室")

st.subheader("1. 檢查 Secrets 狀態")
# 嘗試讀取
try:
    secret_key = st.secrets.get("GOOGLE_API_KEY")
    
    if secret_key:
        # 顯示前 5 碼，確認是否讀取成功
        st.success(f"✅ 抓到了！您的 Key 開頭是：{secret_key[:5]}...")
        
        # 檢查是否不小心貼到了 OpenAI 的 Key
        if secret_key.startswith("sk-"):
            st.error("❌ 這是 OpenAI 的 Key (sk-...)，但我們需要的是 Google 的 (AIza...)")
        elif secret_key.startswith("AIza"):
            st.info("ok 格式正確，是 Google 的 Key。")
            
            # 實際連線測試
            st.subheader("2. 連線測試")
            try:
                genai.configure(api_key=secret_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content("哈囉，連線測試中！")
                st.balloons()
                st.write(f"🎉 AI 回應成功：{response.text}")
            except Exception as e:
                st.error(f"❌ Key 有抓到，但連線失敗：{e}")
                st.write("請確認您的 Key 是否已經在 Google AI Studio 被刪除？")
        else:
            st.warning("⚠️ Key 的格式怪怪的，請確認是否複製完整。")
            
    else:
        st.error("❌ 讀取失敗：st.secrets 裡面是空的，或者找不到 'GOOGLE_API_KEY'。")
        st.write("目前 Secrets 裡有的東西：", st.secrets)

except FileNotFoundError:
    st.error("❌ 找不到 secrets.toml 檔案。請確認您是在 Streamlit Cloud 的 'Secrets' 欄位設定，而不是在本地電腦。")
