import streamlit as st
import pandas as pd
import psycopg2
import plotly.express as px

# --- Fungsi Pengambilan Data (Duplikat dari main.py, bisa direfaktor nanti) ---
@st.cache_resource
def get_db_connection():
    """Membuat koneksi ke database kama_server."""
    # Perlu load_dotenv lagi karena ini halaman terpisah
    from dotenv import load_dotenv
    import os
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../server/.env'))
    
    conn_info = {
        "host": os.getenv("SERVER_DB_HOST", "localhost"),
        "port": int(os.getenv("SERVER_DB_PORT", 5432)),
        "dbname": os.getenv("SERVER_DB_NAME", "kama-server"),
        "user": os.getenv("SERVER_DB_USER", "postgres"),
        "password": os.getenv("SERVER_DB_PASS", "satudua3"),
    }
    try:
        conn = psycopg2.connect(**conn_info)
        return conn
    except psycopg2.OperationalError as e:
        st.error(f"Gagal terhubung ke database: {e}")
        return None

@st.cache_data(ttl=60)
def fetch_historical_data(_conn, box_id):
    """Mengambil seluruh data historis untuk satu box."""
    if _conn is None:
        return pd.DataFrame()
    try:
        query = "SELECT * FROM kama_server WHERE id = %s ORDER BY recorded_at ASC;"
        df = pd.read_sql(query, _conn, params=(box_id,))
        return df
    except Exception as e:
        st.error(f"Gagal mengambil data historis: {e}")
        return pd.DataFrame()

# --- Tampilan Halaman Detail ---
st.set_page_config(layout="wide")

# Ambil box_id dari query parameter
try:
    box_id = int(st.query_params["box_id"])
except (KeyError, ValueError):
    st.error("ID Box tidak valid atau tidak ditemukan.")
    st.page_link("main.py", label="Kembali ke Halaman Utama", icon="🏠")
    st.stop()

st.title(f"📊 Detail Historis - Smartbox #{box_id}")

conn = get_db_connection()
df_history = fetch_historical_data(conn, box_id)

if conn is None:
    st.stop()

if df_history.empty:
    st.warning("Tidak ada data historis untuk box ini.")
    st.page_link("main.py", label="Kembali ke Halaman Utama", icon="🏠")
else:
    latest_record = df_history.iloc[-1]

    st.markdown("---")
    st.subheader("Informasi Terkini")

    # --- Metrik Terkini ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🌡️ Suhu", f"{latest_record['temperature']:.1f} °C")
    col2.metric("💧 Kelembapan", f"{latest_record['humidity']:.1f} %")
    col3.metric("💨 Gas (MQ-135)", f"{latest_record['gas_level']:.0f} ppm")
    
    status = latest_record['status']
    with col4:
        st.markdown("<h6>Status</h6>", unsafe_allow_html=True)
        if status == 'good':
            st.success(f"**{status.capitalize()}**")
        elif status == 'warning':
            st.warning(f"**{status.capitalize()}**")
        else: # bad
            st.error(f"**{status.capitalize()}**")

    # --- Prediksi dan Rekomendasi ---
    st.markdown("---")
    st.subheader("Analisis & Rekomendasi AI")
    
    col_pred, col_recom = st.columns(2)
    
    with col_pred:
        pred_spoil = latest_record['predicted_spoil']
        if pd.notna(pred_spoil):
            st.metric("⏳ Prediksi Busuk", f"{pred_spoil:.1f} hari lagi")
        else:
            st.info("Prediksi belum tersedia.")

    with col_recom:
        recommendation = latest_record['recommendation_text']
        if pd.notna(recommendation):
            with st.expander("Lihat Rekomendasi Pengolahan", expanded=True):
                st.markdown(recommendation)
        else:
            st.info("Tidak ada rekomendasi (makanan dalam kondisi baik).")

    # --- Visualisasi Grafik ---
    st.markdown("---")
    st.subheader("Grafik Historis Sensor")
    
    # Pastikan recorded_at adalah tipe datetime
    df_history['recorded_at'] = pd.to_datetime(df_history['recorded_at'])

    # Grafik Suhu dan Kelembapan
    fig_temp_hum = px.line(df_history, x='recorded_at', y=['temperature', 'humidity'],
                           title='Grafik Suhu & Kelembapan', labels={'value': 'Nilai', 'recorded_at': 'Waktu'},
                           color_discrete_map={'temperature': '#FF6347', 'humidity': '#1E90FF'})
    st.plotly_chart(fig_temp_hum, use_container_width=True)

    # Grafik Gas
    fig_gas = px.area(df_history, x='recorded_at', y='gas_level',
                      title='Grafik Tingkat Gas (MQ-135)', labels={'gas_level': 'PPM', 'recorded_at': 'Waktu'},
                      color_discrete_sequence=['#9A5AFF'])
    st.plotly_chart(fig_gas, use_container_width=True)

    # --- Tabel Data Mentah ---
    st.markdown("---")
    with st.expander("Lihat Data Mentah Historis"):
        st.dataframe(df_history)

    st.page_link("main.py", label="Kembali ke Halaman Utama", icon="🏠")
