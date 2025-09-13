import streamlit as st
import pandas as pd
try:
    import psycopg2
except ModuleNotFoundError:
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

# --- Helper ---
def _get_secret_value(key, default=None):
    """Ambil value dari st.secrets atau os.environ."""
    try:
        val = st.secrets[key]  # type: ignore[attr-defined]
        if val is not None:
            return val
    except Exception:
        pass
    return os.getenv(key, default)

# --- Fungsi Koneksi Database ---
@st.cache_resource
def get_realtime_conn():
    """Koneksi ke DB realtime (kama_realtime)."""
    load_dotenv(os.path.join(os.path.dirname(__file__), '../server/.env'))
    try:
        conn = psycopg2.connect(
            host=_get_secret_value("REALTIME_DB_HOST", "switchback.proxy.rlwy.net"),
            port=int(_get_secret_value("REALTIME_DB_PORT", 5432)),
            dbname=_get_secret_value("REALTIME_DB_NAME", "railway"),
            user=_get_secret_value("REALTIME_DB_USER", "postgres"),
            password=_get_secret_value("REALTIME_DB_PASS", "password"),
            # sslmode=_get_secret_value("REALTIME_DB_SSLMODE", "prefer"),
        )
        return conn
    except Exception as e:
        st.error(f"❌ Gagal connect realtime_db: {e}")
        return None


@st.cache_resource
def get_server_conn():
    """Koneksi ke DB server (kama_server)."""
    load_dotenv(os.path.join(os.path.dirname(__file__), '../server/.env'))
    try:
        conn = psycopg2.connect(
            host=_get_secret_value("SERVER_DB_HOST", "switchback.proxy.rlwy.netst"),
            port=int(_get_secret_value("SERVER_DB_PORT", 5432)),
            dbname=_get_secret_value("SERVER_DB_NAME", "railway"),
            user=_get_secret_value("SERVER_DB_USER", "postgres"),
            password=_get_secret_value("SERVER_DB_PASS", "password"),
            # sslmode=_get_secret_value("SERVER_DB_SSLMODE", "prefer"),
        )
        return conn
    except Exception as e:
        st.error(f"❌ Gagal connect server_db: {e}")
        return None

# --- Query Helper ---
def fetch_latest_data(conn, limit=1):
    if conn is None:
        return pd.DataFrame()
    try:
        q = f"SELECT * FROM kama_realtime ORDER BY recorded_at DESC LIMIT {limit};"
        return pd.read_sql(q, conn)
    except Exception as e:
        st.error(f"Gagal ambil data realtime: {e}")
        return pd.DataFrame()

def fetch_history(conn, rows=100):
    if conn is None:
        return pd.DataFrame()
    try:
        q = f"SELECT * FROM kama_realtime ORDER BY recorded_at DESC LIMIT {rows};"
        return pd.read_sql(q, conn)
    except Exception as e:
        st.error(f"Gagal ambil history: {e}")
        return pd.DataFrame()

def fetch_latest_prediction(conn):
    if conn is None:
        return None
    try:
        q = "SELECT * FROM kama_server ORDER BY recorded_at DESC LIMIT 1;"
        df = pd.read_sql(q, conn)
        return None if df.empty else df.iloc[0]
    except Exception as e:
        st.warning(f"Gagal ambil prediksi: {e}")
        return None

# --- Tampilan Utama ---
st.title("📦 KAMA Smartbox")
st.markdown("Monitoring realtime makanan oleh KAMA Smartbox")

realtime_conn = get_realtime_conn()
server_conn = get_server_conn()

# Auto-refresh 10 detik
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=10_000, key="kama_autorefresh")
except Exception:
    last_trigger = st.session_state.get('_last_refresh', 0)
    now = time.time()
    if now - last_trigger > 10:
        st.session_state['_last_refresh'] = now
        st.experimental_rerun()

latest = fetch_latest_data(realtime_conn, 1)
if latest.empty:
    st.warning("Tidak ada data realtime di `kama_realtime`.")
else:
    row = latest.iloc[0]
    st.subheader("Smartbox Realtime")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.metric("🌡️ Suhu", f"{row['temperature']:.1f} °C")
        st.metric("💧 Kelembapan", f"{row['humidity']:.1f} %")
        st.metric("💨 Gas Amonia", f"{row['gas_level']:.0f} ppm")
    with col2:
        status = str(row.get('status', 'Unknown')).capitalize()
        if status.lower() == "good":
            st.success(f"✅ Status: {status}")
        elif status.lower() == "warning":
            st.warning(f"⚠️ Status: {status}")
        elif status.lower() == "bad":
            st.error(f"❌ Status: {status}")
        else:
            st.info(f"ℹ️ Status: {status}")

    # Detail + grafik
    with st.expander("Lihat detail historis & prediksi"):
        hist = fetch_history(realtime_conn, 500)
        pred = fetch_latest_prediction(server_conn)

        if not hist.empty:
            hist['recorded_at'] = pd.to_datetime(hist['recorded_at'])
            if pred is not None and 'predicted_spoil' in pred:
                try:
                    val = float(pred['predicted_spoil'])
                    if val < 0:
                        txt = f"Busuk {abs(val*24):.1f} jam yang lalu"
                    elif val < 1:
                        txt = f"Dalam {val*24:.1f} jam"
                    else:
                        txt = f"Dalam {val:.1f} hari"
                    st.metric("⏳ Prediksi Busuk", txt)
                except:
                    pass

            # Grafik suhu & kelembapan
            try:
                fig1 = px.line(hist.sort_values('recorded_at'), x='recorded_at',
                               y=['temperature', 'humidity'],
                               title="Grafik Suhu & Kelembapan")
                st.plotly_chart(fig1, use_container_width=True)
            except Exception as e:
                st.warning(f"Gagal grafik suhu/kelembapan: {e}")

            # Grafik gas
            try:
                fig2 = px.area(hist.sort_values('recorded_at'), x='recorded_at',
                               y='gas_level', title="Grafik Gas (MQ-135)")
                st.plotly_chart(fig2, use_container_width=True)
            except Exception as e:
                st.warning(f"Gagal grafik gas: {e}")

            st.dataframe(hist[['recorded_at','temperature','humidity','gas_level','status']].head(100))
        else:
            st.info("Tidak ada data historis.")

# --- Chatbot ---
st.markdown("---")
st.subheader("🤖 Chatbot KAMA")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Tanyakan tentang makanan atau sensor...")
if prompt:
    st.session_state.chat_history.append({"role":"user","content":prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        msg = st.empty()
        reply = ""
        key = _get_secret_value("GEMINI_API_KEY")
        if key:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                for r in model.generate_content(
                    f"Anda adalah AI KAMA Smartbox. Jawab singkat dalam Bahasa Indonesia.\nPertanyaan: {prompt}",
                    stream=True
                ):
                    reply += r.text or ""
                    msg.markdown(reply + "▌")
                msg.markdown(reply)
            except Exception as e:
                reply = f"Maaf, error AI: {e}"
                msg.markdown(reply)
        else:
            reply = "Fitur AI belum aktif. Tambahkan GEMINI_API_KEY di secrets/.env."
            msg.markdown(reply)

    st.session_state.chat_history.append({"role":"assistant","content":reply})
