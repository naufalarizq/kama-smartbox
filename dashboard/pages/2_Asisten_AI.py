import streamlit as st
import google.generativeai as genai
import os

# --- Konfigurasi Chatbot ---
st.set_page_config(page_title="Asisten KAMA", page_icon="🤖")
st.title("🤖 Asisten AI KAMA")
st.write("Punya pertanyaan? Tanyakan pada asisten AI kami!")

# Ambil API Key dari .env di folder server
# Sebaiknya ini dijadikan environment variable di sistem deployment nanti
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../server/.env'))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        st.error("Kunci API Gemini tidak ditemukan. Mohon konfigurasikan di file `.env`.")
        st.stop()
    genai.configure(api_key=GEMINI_API_KEY)
except ImportError:
    st.error("Gagal mengimpor `python-dotenv`. Pastikan library sudah terinstal.")
    st.stop()

# Inisialisasi model Generative AI
model = genai.GenerativeModel('gemini-1.5-flash')

# Inisialisasi riwayat chat di session state Streamlit
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Tampilkan riwayat chat
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Terima input dari pengguna
if prompt := st.chat_input("Tanya seputar kelayakan makanan..."):
    # Tambahkan pesan pengguna ke riwayat
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Dapatkan respons dari AI
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # Konteks awal untuk AI
        contextual_prompt = f"""
        Anda adalah Asisten AI untuk KAMA Smartbox. 
        Tugas Anda adalah menjawab pertanyaan pengguna seputar:
        1. Cara penggunaan KAMA Smartbox.
        2. Tips menyimpan makanan (buah dan sayur).
        3. Tanda-tanda kelayakan makanan secara umum.
        4. Manfaat memantau suhu, kelembapan, dan gas.
        
        Jawab dengan ramah, informatif, dan dalam Bahasa Indonesia.
        
        Pertanyaan pengguna: "{prompt}"
        """
        
        try:
            # Menggunakan stream untuk respons yang lebih interaktif
            responses = model.generate_content(contextual_prompt, stream=True)
            for response in responses:
                full_response += (response.text or "")
                message_placeholder.markdown(full_response + "▌")
            message_placeholder.markdown(full_response)
        except Exception as e:
            full_response = f"Maaf, terjadi kesalahan saat menghubungi AI: {e}"
            message_placeholder.markdown(full_response)

    # Tambahkan respons AI ke riwayat
    st.session_state.chat_history.append({"role": "assistant", "content": full_response})
