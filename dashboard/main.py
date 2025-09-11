import streamlit as st
import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv

# --- Konfigurasi Halaman ---
st.set_page_config(
    page_title="KAMA Smartbox Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Fungsi Koneksi Database ---
# Menggunakan st.cache_resource agar koneksi di-cache dan tidak dibuat ulang setiap interaksi
@st.cache_resource
def get_db_connection():
    """Membuat koneksi ke database kama_server."""
    load_dotenv(os.path.join(os.path.dirname(__file__), '../server/.env'))
    
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
        st.info("Pastikan server Flask (app.py) dan database PostgreSQL sedang berjalan.")
        return None

# --- Fungsi Pengambilan Data ---
# Menggunakan st.cache_data agar data di-cache. TTL (time-to-live) 60 detik.
@st.cache_data(ttl=60)
def fetch_latest_data(_conn):
    """Mengambil data terbaru dari setiap 'box'."""
    if _conn is None:
        return pd.DataFrame()
    try:
        # Untuk prototipe, kita asumsikan setiap 'id' unik adalah 'box' yang berbeda.
        # Query ini mengambil baris terakhir untuk setiap ID unik.
        query = """
        SELECT t1.*
        FROM kama_server t1
        INNER JOIN (
            SELECT id, MAX(recorded_at) as max_recorded_at
            FROM kama_server
            GROUP BY id
        ) t2 ON t1.id = t2.id AND t1.recorded_at = t2.max_recorded_at
        ORDER BY t1.recorded_at DESC;
        """
        df = pd.read_sql(query, _conn)
        return df
    except Exception as e:
        st.error(f"Gagal mengambil data: {e}")
        return pd.DataFrame()

# --- Tampilan Utama ---
st.title("📦 Dashboard KAMA Smartbox")
st.markdown("Selamat datang! Pantau semua kotak penyimpanan pintar Anda di satu tempat.")

conn = get_db_connection()
latest_data_df = fetch_latest_data(conn)

if conn is None:
    st.stop()

if latest_data_df.empty:
    st.warning("Tidak ada data untuk ditampilkan. Pastikan data sudah masuk ke database `kama-server`.")
else:
    st.markdown("---")
    
    # --- Tampilan Widget ---
    # Menggunakan kolom untuk responsivitas di mobile
    cols = st.columns(3) # Ubah angka ini untuk jumlah widget per baris di desktop
    col_idx = 0

    for index, row in latest_data_df.iterrows():
        # Pilih kolom saat ini, lalu putar ke kolom berikutnya
        current_col = cols[col_idx % len(cols)]
        col_idx += 1

        with current_col:
            with st.container(border=True):
                # Asumsikan ID unik sebagai nama Box untuk prototipe
                st.subheader(f"Smartbox #{row['id']}", divider="rainbow")
                
                # Tampilkan metrik utama
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(label="🌡️ Suhu", value=f"{row['temperature']:.1f} °C")
                    st.metric(label="💧 Kelembapan", value=f"{row['humidity']:.1f} %")
                with col2:
                    st.metric(label="💨 Gas (MQ-135)", value=f"{row['gas_level']:.0f} ppm")
                    
                    # Beri warna pada status
                    status = row['status'].capitalize()
                    if status == 'Good':
                        st.metric(label="✅ Status", value=status)
                    elif status == 'Warning':
                        st.metric(label="⚠️ Status", value=status)
                    else: # Bad
                        st.metric(label="❌ Status", value=status)

                # Tombol untuk melihat detail
                st.link_button("Lihat Detail Historis", f"/Detail_Box?box_id={row['id']}")

st.sidebar.success("Pilih halaman di atas untuk navigasi.")
st.sidebar.info("Dashboard ini akan refresh data setiap 60 detik.")
