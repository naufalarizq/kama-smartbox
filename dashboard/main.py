import streamlit as st
import pandas as pd
try:
    import psycopg2  # Prefer psycopg2 if available
except ModuleNotFoundError:  # Fallback to psycopg (v3)
    import psycopg as psycopg2  # type: ignore
import os
import plotly.express as px
import time
from dotenv import load_dotenv
import google.generativeai as genai

# --- Konfigurasi Halaman ---
st.set_page_config(
    page_title="KAMA Smartbox Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

"""
Helper konfigurasi: baca kredensial dari st.secrets (Streamlit Cloud) terlebih dahulu,
fallback ke variabel environment (.env) dan default hard-coded.
"""

def _get_secrets_section(*names):
    """Ambil dict secrets pertama yang tersedia dari daftar nama section."""
    try:
        for name in names:
            try:
                sec = st.secrets.get(name)  # type: ignore[attr-defined]
            except Exception:
                sec = None
            if isinstance(sec, dict) and sec:
                return sec
    except Exception:
        pass
    return None

def _get_secret_value(key, default=None):
    """Ambil nilai dari st.secrets (top-level) atau os.environ."""
    try:
        val = st.secrets.get(key)  # type: ignore[attr-defined]
        if val is not None:
            return val
    except Exception:
        pass
    return os.getenv(key, default)

# --- Fungsi Koneksi Database ---
# Menggunakan st.cache_resource agar koneksi di-cache dan tidak dibuat ulang setiap interaksi
@st.cache_resource
def get_db_connection():
    """Membuat koneksi ke database kama_server."""
    load_dotenv(os.path.join(os.path.dirname(__file__), '../server/.env'))

    # Prefer secrets: realtime_db -> db -> postgres -> database
    sec = _get_secrets_section("realtime_db", "db", "postgres", "database")
    host = (sec.get("host") if sec else None) or _get_secret_value("SERVER_DB_HOST", "localhost")
    port = int((sec.get("port") if sec else None) or _get_secret_value("SERVER_DB_PORT", 5432))
    user = (sec.get("user") if sec else None) or _get_secret_value("SERVER_DB_USER", "postgres")
    password = (sec.get("password") if sec else None) or _get_secret_value("SERVER_DB_PASS", "satudua3")

    # Build list of candidate database names to try (order: secrets, server var, common names, fallback)
    candidates = []
    # from secrets section
    if sec:
        for key in ("dbname", "database", "name"):
            if sec.get(key):
                candidates.append(str(sec.get(key)))
                break
    # from environment
    if _get_secret_value("SERVER_DB_NAME"):
        candidates.append(_get_secret_value("SERVER_DB_NAME"))
    if _get_secret_value("DB_NAME"):
        candidates.append(_get_secret_value("DB_NAME"))
    # common names used in project
    candidates.extend(["kama-realtime", "kama_realtime", "kama-server", "kama_server"])

    last_err = None
    for dbname in candidates:
        if dbname in (None, ''):
            continue
        try:
            conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
            # quick check: does table kama_realtime exist in this DB?
            with conn.cursor() as cur:
                try:
                    cur.execute("SELECT 1 FROM kama_realtime LIMIT 1;")
                    # success -> return this connection
                    return conn
                except Exception:
                    # table missing in this DB; close and try next
                    conn.close()
                    last_err = f"Tabel kama_realtime tidak ditemukan di database '{dbname}'."
                    continue
        except psycopg2.OperationalError as e:
            last_err = str(e)
            continue

    # Jika sampai sini, tidak ada koneksi/DB yang cocok
    st.error("Gagal terhubung ke database yang berisi tabel `kama_realtime`.")
    if last_err:
        st.info(str(last_err))
    st.info("Periksa file server/.env atau jalankan SQL schema di database yang benar. Contoh nama DB yang dicari: " + ",".join(candidates))
    return None


@st.cache_resource
def get_server_db_connection():
    """Membuat koneksi ke database yang berisi tabel `kama_server`.
    Membaca environment SERVER_DB_NAME atau DB_NAME sebagai fallback.
    """
    load_dotenv(os.path.join(os.path.dirname(__file__), '../server/.env'))

    # Prefer secrets: server_db -> db -> postgres -> database
    sec = _get_secrets_section("server_db", "db", "postgres", "database")
    host = (sec.get("host") if sec else None) or _get_secret_value("SERVER_DB_HOST", "localhost")
    port = int((sec.get("port") if sec else None) or _get_secret_value("SERVER_DB_PORT", 5432))
    user = (sec.get("user") if sec else None) or _get_secret_value("SERVER_DB_USER", "postgres")
    password = (sec.get("password") if sec else None) or _get_secret_value("SERVER_DB_PASS", "satudua3")

    candidates = []
    # from secrets section
    if sec:
        for key in ("dbname", "database", "name"):
            if sec.get(key):
                candidates.append(str(sec.get(key)))
                break
    # from environment
    if _get_secret_value("SERVER_DB_NAME"):
        candidates.append(_get_secret_value("SERVER_DB_NAME"))
    if _get_secret_value("DB_NAME"):
        candidates.append(_get_secret_value("DB_NAME"))
    candidates.extend(["kama-server", "kama_server"])

    last_err = None
    for dbname in candidates:
        if dbname in (None, ''):
            continue
        try:
            conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
            with conn.cursor() as cur:
                try:
                    cur.execute("SELECT 1 FROM kama_server LIMIT 1;")
                    return conn
                except Exception:
                    conn.close()
                    last_err = f"Tabel kama_server tidak ditemukan di database '{dbname}'."
                    continue
        except psycopg2.OperationalError as e:
            last_err = str(e)
            continue

    st.warning("Tidak dapat menemukan database yang berisi tabel `kama_server`. Prediksi tidak akan tampil.")
    if last_err:
        st.info(last_err)
    return None

# --- Fungsi Pengambilan Data ---
def fetch_latest_data(_conn, limit=1):
    """Mengambil data realtime terbaru dari tabel `kama_realtime` (most recent).
    Tidak menggunakan cache agar selalu mendapatkan data terbaru dari DB.
    """
    if _conn is None:
        return pd.DataFrame()
    try:
        query = f"""
        SELECT * FROM kama_realtime
        ORDER BY recorded_at DESC
        LIMIT {limit};
        """
        df = pd.read_sql(query, _conn)
        return df
    except Exception as e:
        st.error(f"Gagal mengambil data: {e}")
        return pd.DataFrame()


def fetch_history(_conn, rows=100):
    if _conn is None:
        return pd.DataFrame()
    try:
        # Ambil history sensor dari kama_realtime untuk visualisasi waktu nyata
        query = f"SELECT * FROM kama_realtime ORDER BY recorded_at DESC LIMIT {rows};"
        return pd.read_sql(query, _conn)
    except Exception as e:
        st.error(f"Gagal mengambil history: {e}")
        return pd.DataFrame()


def fetch_latest_prediction(_conn_server):
    """Ambil record terbaru dari `kama_server` yang berisi predicted_spoil dan recommendation_text.
    Kita pakai ini untuk menampilkan prediksi / rekomendasi (bisa sedikit lebih lama daripada data realtime).
    """
    if _conn_server is None:
        return None
    try:
        query = "SELECT * FROM kama_server ORDER BY recorded_at DESC LIMIT 1;"
        df = pd.read_sql(query, _conn_server)
        if df.empty:
            return None
        return df.iloc[0]
    except Exception as e:
        st.warning(f"Gagal mengambil prediksi terbaru: {e}")
        return None

# --- Tampilan Utama ---
st.title("📦 KAMA Smartbox")
st.markdown("Selamat datang! Monitoring realtime makanana oleh KAMA Smartbox.")

realtime_conn = get_db_connection()
server_conn = get_server_db_connection()
if realtime_conn is None and server_conn is None:
    st.stop()

# Auto-refresh setiap 10 detik: coba gunakan streamlit-autorefresh jika tersedia, jika tidak gunakan time-based rerun
auto_refresh_available = False
try:
    from streamlit_autorefresh import st_autorefresh
    auto_refresh_available = True
except Exception:
    auto_refresh_available = False

if auto_refresh_available:
    st_autorefresh(interval=10_000, key="kama_autorefresh")
else:
    # fallback: lakukan rerun setiap 10 detik menggunakan waktu simple
    # Sederhana: jika belum ada timestamp di session, set; jika beda >10s, rerun
    last_trigger = st.session_state.get('_last_refresh_ts', None)
    now_ts = time.time()
    if last_trigger is None or (now_ts - last_trigger) > 10:
        st.session_state['_last_refresh_ts'] = now_ts
        st.experimental_rerun()

# Ambil data realtime terbaru tiap kali halaman render (tidak cached)
latest = fetch_latest_data(realtime_conn, limit=1)
if latest.empty:
    st.warning("Tidak ada data realtime. Pastikan ada data di `kama-server`.")
else:
    row = latest.iloc[0]
    container = st.container()
    with container:
        st.subheader(f"Smartbox Realtime")
        col1, col2 = st.columns([2,1])
        with col1:
            st.metric(label="🌡️ Suhu", value=f"{row['temperature']:.1f} °C")
            st.metric(label="💧 Kelembapan", value=f"{row['humidity']:.1f} %")
            st.metric(label="💨 Gas Amonia", value=f"{row['gas_level']:.0f} ppm")
        with col2:
            status = str(row.get('status', 'Unknown')).capitalize()
            if status.lower() == 'good':
                st.success(f"✅ Status: {status}")
            elif status.lower() == 'warning':
                st.warning(f"⚠️ Status: {status}")
            elif status.lower() == 'bad':
                st.error(f"❌ Status: {status}")
            else:
                st.info(f"ℹ️ Status: {status}")

        # Inline detail (tidak pindah tab)
        with st.expander("Lihat detail historis & prediksi (inline)"):
            # Ambil data historis terbaru untuk visualisasi dan analisis
            hist_df = fetch_history(realtime_conn, rows=500)
            # Ambil prediksi terbaru dari kama_server (jika tersedia)
            pred_row = fetch_latest_prediction(server_conn)
            if hist_df.empty:
                st.write("Tidak ada data historis.")
            else:
                # pastikan kolom datetime
                hist_df['recorded_at'] = pd.to_datetime(hist_df['recorded_at'])

                # Tampilkan prediksi busuk (predicted_spoil) dan rekomendasi dari tabel kama_server
                colp, colr = st.columns(2)
                with colp:
                    if pred_row is not None and 'predicted_spoil' in pred_row.index and pd.notna(pred_row['predicted_spoil']):
                        try:
                            ps_val = float(pred_row['predicted_spoil'])
                            # Jika negatif -> sudah busuk: tampilkan sebagai jam yang lalu
                            if ps_val < 0:
                                hours_ago = abs(ps_val) * 24.0
                                display_text = f"Busuk {hours_ago:.1f} jam yang lalu"
                            else:
                                # Jika kurang dari 1 hari, tampilkan dalam jam tersisa
                                if ps_val < 1.0:
                                    hours = ps_val * 24.0
                                    display_text = f"Dalam {hours:.1f} jam"
                                else:
                                    display_text = f"Dalam {ps_val:.1f} hari"
                            st.metric("⏳ Prediksi Busuk (terbaru)", display_text)
                        except Exception:
                            st.metric("⏳ Prediksi Busuk (terbaru)", f"{float(pred_row['predicted_spoil']):.1f} hari")
                    else:
                        st.info("Prediksi busuk belum tersedia untuk data terbaru.")
                with colr:
                    # Tampilkan rekomendasi hanya jika status untuk record prediksi adalah 'bad'
                    show_recom = False
                    try:
                        if pred_row is not None and 'status' in pred_row.index and str(pred_row['status']).lower() == 'bad':
                            show_recom = True
                    except Exception:
                        show_recom = False

                    if show_recom and pred_row is not None and 'recommendation_text' in pred_row.index and pd.notna(pred_row['recommendation_text']):
                        with st.expander("Lihat Rekomendasi Pengolahan", expanded=False):
                            st.markdown(pred_row['recommendation_text'])
                    else:
                        st.info("Tidak ada rekomendasi untuk data terbaru.")

                # Grafik Suhu & Kelembapan
                try:
                    fig_temp_hum = px.line(hist_df.sort_values('recorded_at'), x='recorded_at', y=['temperature', 'humidity'],
                                           title='Grafik Suhu & Kelembapan', labels={'value': 'Nilai', 'recorded_at': 'Waktu'})
                    st.plotly_chart(fig_temp_hum, use_container_width=True)
                except Exception as e:
                    st.warning(f"Gagal membuat grafik Suhu/Kelembapan: {e}")

                # Grafik Gas
                try:
                    fig_gas = px.area(hist_df.sort_values('recorded_at'), x='recorded_at', y='gas_level',
                                      title='Grafik Tingkat Gas (MQ-135)', labels={'gas_level': 'PPM', 'recorded_at': 'Waktu'})
                    st.plotly_chart(fig_gas, use_container_width=True)
                except Exception as e:
                    st.warning(f"Gagal membuat grafik Gas: {e}")

                # Tampilkan tabel ringkas (100 baris teratas)
                st.markdown("---")
                # Tampilkan tabel ringkas (100 baris teratas)
                cols_to_show = ['recorded_at','temperature','humidity','gas_level','status']
                if 'predicted_spoil' in hist_df.columns:
                    cols_to_show.append('predicted_spoil')
                st.dataframe(hist_df[cols_to_show].head(100))

        # Embedded chatbot widget (ringkas)
        st.markdown("---")
        st.subheader("🤖 Chatbot KAMA")
        # Inisialisasi riwayat chat di session state Streamlit
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"]) 

        # Ambil API Key untuk Gemini (opsional) dari st.secrets lalu .env
        GEMINI_API_KEY = None
        try:
            # coba dari secrets dulu
            GEMINI_API_KEY = _get_secret_value("GEMINI_API_KEY")
            if GEMINI_API_KEY:
                genai.configure(api_key=GEMINI_API_KEY)
        except Exception:
            GEMINI_API_KEY = None

        prompt = st.chat_input("Tanyakan tentang penggunaan atau kelayakan makanan...")
        if prompt:
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                contextual_prompt = f"""
                Anda adalah Asisten AI untuk KAMA Smartbox. Tugas Anda adalah menjawab pertanyaan pengguna seputar penggunaan KAMA, tips menyimpan makanan, tanda kelayakan, dan interpretasi sensor.
                Jawab dalam Bahasa Indonesia.
                Pertanyaan pengguna: \"{prompt}\"
                """
                if GEMINI_API_KEY:
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        responses = model.generate_content(contextual_prompt, stream=True)
                        for response in responses:
                            full_response += (response.text or "")
                            message_placeholder.markdown(full_response + "▌")
                        message_placeholder.markdown(full_response)
                    except Exception as e:
                        full_response = f"Maaf, terjadi kesalahan saat menghubungi AI: {e}"
                        message_placeholder.markdown(full_response)
                else:
                    full_response = "Fitur AI belum dikonfigurasi. Tambahkan GEMINI_API_KEY di server/.env untuk mengaktifkan chatbot."
                    message_placeholder.markdown(full_response)

            st.session_state.chat_history.append({"role": "assistant", "content": full_response})

# st.sidebar.title("Navigasi")
# st.sidebar.write("Pilih halaman:")
# st.sidebar.markdown("- Main (dashboard)")
# st.sidebar.markdown("- Chatbot (halaman penuh jika ingin)")
