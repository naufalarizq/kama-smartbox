import streamlit as st
import pandas as pd
import os
import time
import plotly.express as px
from dotenv import load_dotenv
try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2  # type: ignore
import joblib
import gdown
from pathlib import Path
import numpy as np
import google.generativeai as genai

# --- Konfigurasi Halaman ---
st.set_page_config(
    page_title="KAMA Smartbox Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Secrets helper ---
def _get_secret_value(key, default=None):
    try:
        val = st.secrets[key]  # type: ignore[attr-defined]
        if val is not None:
            return val
    except Exception:
        pass
    return os.getenv(key, default)

# --- DB connections ---
@st.cache_resource
def get_realtime_conn():
    load_dotenv(os.path.join(os.path.dirname(__file__), '../server/.env'))
    try:
        return psycopg2.connect(
            host=_get_secret_value("REALTIME_DB_HOST"),
            port=int(_get_secret_value("REALTIME_DB_PORT")),
            dbname=_get_secret_value("REALTIME_DB_NAME"),
            user=_get_secret_value("REALTIME_DB_USER"),
            password=_get_secret_value("REALTIME_DB_PASS"),
            sslmode=_get_secret_value("REALTIME_DB_SSLMODE", "require"),
        )
    except Exception as e:
        st.error(f"❌ Gagal connect realtime_db: {e}")
        return None

@st.cache_resource
def get_server_conn():
    load_dotenv(os.path.join(os.path.dirname(__file__), '../server/.env'))
    try:
        return psycopg2.connect(
            host=_get_secret_value("SERVER_DB_HOST"),
            port=int(_get_secret_value("SERVER_DB_PORT")),
            dbname=_get_secret_value("SERVER_DB_NAME"),
            user=_get_secret_value("SERVER_DB_USER"),
            password=_get_secret_value("SERVER_DB_PASS"),
            sslmode=_get_secret_value("SERVER_DB_SSLMODE", "require"),
        )
    except Exception as e:
        st.error(f"❌ Gagal connect server_db: {e}")
        return None

# --- Query helpers ---
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

# --- Models from Google Drive ---
STATUS_MODEL_URL = "https://drive.google.com/file/d/1XKjJVLBKBLZtTCGxeSsCpLkk9e-IT-IA/view?usp=sharing"
SPOIL_MODEL_URL = "https://drive.google.com/file/d/1VoDO2brU5gFXJOZnYOFdaCl0Y_0RWLUy/view?usp=sharing"

@st.cache_resource
def _ensure_models_dir() -> Path:
    d = Path(__file__).parent / ".cache_models"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _unwrap_model(loaded):
    if isinstance(loaded, dict):
        for k in ["models", "model", "estimator", "clf", "xgb"]:
            if k in loaded:
                cand = loaded[k]
                if isinstance(cand, dict):
                    for _k, _v in cand.items():
                        if hasattr(_v, "predict"):
                            return _v
                if hasattr(cand, "predict"):
                    return cand
    return loaded

@st.cache_resource(show_spinner=True)
def load_status_model():
    models_dir = _ensure_models_dir()
    dest = models_dir / "status_model.pkl"
    if not dest.exists():
        gdown.download(STATUS_MODEL_URL, str(dest), quiet=False, fuzzy=True)
    return _unwrap_model(joblib.load(dest))

@st.cache_resource(show_spinner=True)
def load_spoil_model():
    models_dir = _ensure_models_dir()
    dest = models_dir / "spoil_model.pkl"
    if not dest.exists():
        gdown.download(SPOIL_MODEL_URL, str(dest), quiet=False, fuzzy=True)
    return _unwrap_model(joblib.load(dest))

def predict_with_models(row: pd.Series):
    """Return (status_label:str, spoil_days:float) using loaded models.
    Features: temperature, humidity, gas_level, jenis_makanan.
    """
    status_model = load_status_model()
    spoil_model = load_spoil_model()
    jenis = row.get("jenis_makanan") or row.get("jenis") or "fruits"
    X = pd.DataFrame([
        {
            "temperature": float(row.get("temperature", np.nan)),
            "humidity": float(row.get("humidity", np.nan)),
            "gas_level": float(row.get("gas_level", np.nan)),
            "jenis_makanan": jenis,
        }
    ])
    # status label
    pred_idx = status_model.predict(X)[0]
    label = None
    if hasattr(status_model, "classes_"):
        try:
            label = str(status_model.classes_[int(pred_idx)])
        except Exception:
            label = None
    if label is None or (isinstance(label, str) and label.isdigit()):
        label_map = {0: "bad", 1: "good", 2: "warning"}
        try:
            label = label_map.get(int(pred_idx), str(pred_idx))
        except Exception:
            label = str(pred_idx)
    # spoil days
    spoil_days = float(spoil_model.predict(X)[0])
    return label, spoil_days

def render_llm_recommendation(jenis_makanan: str, spoil_info: str):
    key = _get_secret_value("GEMINI_API_KEY")
    if not key:
        st.info("Tambahkan GEMINI_API_KEY di secrets/.env untuk rekomendasi AI.")
        return
    try:
        genai.configure(api_key=key)
        prompt = (
            f"Makanan dengan jenis '{jenis_makanan}' telah dinyatakan busuk. {spoil_info} "
            "Berikan 2-3 ide singkat dan praktis untuk mengolahnya agar tidak menjadi sampah, "
            "misalnya dijadikan kompos atau pupuk organik cair. Jawaban harus dalam format daftar bernomor."
        )
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        st.markdown(resp.text)
    except Exception as e:
        st.warning(f"Gagal mendapatkan rekomendasi AI: {e}")

# --- UI ---
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
    # Predict status and spoilage
    try:
        pred_label, pred_spoil_days = predict_with_models(row)
    except Exception as e:
        st.warning(f"Gagal prediksi model: {e}")
        pred_label, pred_spoil_days = (str(row.get('status', 'unknown')).lower(), None)

    with col2:
        label_cap = pred_label.capitalize()
        if pred_label == "good":
            st.success(f"✅ Status: {label_cap}")
        elif pred_label == "warning":
            st.warning(f"⚠️ Status: {label_cap}")
        elif pred_label == "bad":
            st.error(f"❌ Status: {label_cap}")
        else:
            st.info(f"ℹ️ Status: {label_cap}")

    # Detail + grafik
    with st.expander("Lihat detail historis & prediksi"):
        hist = fetch_history(realtime_conn, 500)
        if not hist.empty:
            hist['recorded_at'] = pd.to_datetime(hist['recorded_at'])
            # Prediksi busuk
            if pred_spoil_days is not None:
                if pred_spoil_days < 0:
                    txt = f"Busuk {abs(pred_spoil_days*24):.1f} jam yang lalu"
                elif pred_spoil_days < 1:
                    txt = f"Dalam {pred_spoil_days*24:.1f} jam"
                else:
                    txt = f"Dalam {pred_spoil_days:.1f} hari"
                st.metric("⏳ Prediksi Busuk", txt)

            # Rekomendasi LLM jika status 'bad'
            if pred_label == 'bad':
                jenis = row.get('jenis_makanan') or row.get('jenis') or 'buah-buahan'
                render_llm_recommendation(jenis, "Makanan dinyatakan busuk oleh model.")

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
