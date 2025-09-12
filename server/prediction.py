import os
try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2  # type: ignore
import pandas as pd
import joblib
try:
    from psycopg2.extras import execute_values
except ModuleNotFoundError:
    from psycopg.extras import execute_values  # type: ignore

# --- Konfigurasi ---
# Database Sumber (Real-time data dari sensor)
REALTIME_DB_CONFIG = {
    "host": os.getenv("REALTIME_DB_HOST", "localhost"),
    "port": int(os.getenv("REALTIME_DB_PORT", 5432)),
    "dbname": os.getenv("REALTIME_DB_NAME", "kama-realtime"),
    "user": os.getenv("REALTIME_DB_USER", "postgres"),
    "password": os.getenv("REALTIME_DB_PASS", "satudua3"),
}

# Database Tujuan (Data untuk training dan analisis)
SERVER_DB_CONFIG = {
    "host": os.getenv("SERVER_DB_HOST", "localhost"),
    "port": int(os.getenv("SERVER_DB_PORT", 5432)),
    "dbname": os.getenv("SERVER_DB_NAME", "kama-server"),
    "user": os.getenv("SERVER_DB_USER", "postgres"),
    "password": os.getenv("SERVER_DB_PASS", "satudua3"),
}

# Path ke model prediksi
MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ai/models/xgb_predicted_spoiled.pkl'))

# Nama tabel
REALTIME_TABLE = "kama_realtime"
SERVER_TABLE = "kama_server"

def get_db_connection(config):
    """Membuat koneksi baru ke database."""
    return psycopg2.connect(**config)

def transfer_new_data(realtime_conn, server_conn):
    """
    Transfer data baru dari kama_realtime ke kama_server.
    Mengembalikan daftar ID baris yang baru ditransfer.
    """
    print("Mencari data baru untuk ditransfer...")
    
    # Asumsi: kolom 'recorded_at' unik untuk setiap entri
    # Ambil timestamp terakhir dari server_db
    with server_conn.cursor() as server_cur:
        server_cur.execute(f"SELECT MAX(recorded_at) FROM {SERVER_TABLE}")
        last_timestamp = server_cur.fetchone()[0]

    # Ambil data baru dari realtime_db
    with realtime_conn.cursor() as realtime_cur:
        if last_timestamp:
            print(f"Mengambil data setelah {last_timestamp}...")
            realtime_cur.execute(
                f"SELECT id, battery, temperature, humidity, gas_level, status, recorded_at FROM {REALTIME_TABLE} WHERE recorded_at > %s",
                (last_timestamp,)
            )
        else:
            print("Mengambil semua data (transfer pertama kali)...")
            realtime_cur.execute(
                f"SELECT id, battery, temperature, humidity, gas_level, status, recorded_at FROM {REALTIME_TABLE}"
            )
        
        new_data = realtime_cur.fetchall()
        if not new_data:
            print("Tidak ada data baru yang ditemukan.")
            return []

        print(f"Ditemukan {len(new_data)} baris data baru.")
        
        # Kolom di kama_server: id, battery, temperature, humidity, gas_level, status, recorded_at
        # Sesuaikan jika nama kolom berbeda
        insert_query = f"""
            INSERT INTO {SERVER_TABLE} (id, battery, temperature, humidity, gas_level, status, recorded_at)
            VALUES %s
            ON CONFLICT (id) DO NOTHING
            RETURNING id;
        """
        
        with server_conn.cursor() as server_cur_insert:
            # `execute_values` efisien untuk bulk insert
            inserted_ids = execute_values(
                server_cur_insert, insert_query, new_data, fetch=True
            )
            server_conn.commit()
            
            newly_inserted_ids = [item[0] for item in inserted_ids]
            print(f"Berhasil mentransfer {len(newly_inserted_ids)} baris data baru.")
            return newly_inserted_ids

def predict_and_update(server_conn, new_ids):
    """
    Melakukan prediksi pada data baru dan mengupdate kolom predicted_spoil.
    """
    if not new_ids:
        print("Tidak ada data untuk diprediksi.")
        return

    print(f"Memuat model dari {MODEL_PATH}...")
    try:
        loaded_obj = joblib.load(MODEL_PATH)
        
        # Cek jika file .pkl berisi dictionary, dan ekstrak model dari dalamnya
        if isinstance(loaded_obj, dict):
            print("Model file adalah dictionary. Mencari model di dalamnya...")
            # Coba kunci umum yang biasa digunakan
            for key in ['model', 'estimator', 'predictor', 'xgb']:
                if key in loaded_obj and hasattr(loaded_obj[key], 'predict'):
                    model = loaded_obj[key]
                    print(f"Model ditemukan dalam kunci: '{key}'")
                    break
            else:
                raise ValueError(f"Tidak dapat menemukan objek model yang valid di dalam dictionary. Kunci yang tersedia: {list(loaded_obj.keys())}")
        else:
            model = loaded_obj

    except Exception as e:
        print(f"Error memuat model: {e}")
        return

    # Ambil data yang baru dimasukkan untuk prediksi
    # Pastikan kolom yang diambil sesuai dengan yang dibutuhkan model
    query = f"SELECT id, temperature, humidity, gas_level, jenis_makanan FROM {SERVER_TABLE} WHERE id = ANY(%s)"
    
    df = pd.read_sql_query(query, server_conn, params=(new_ids,))
    if df.empty:
        print("Dataframe kosong, tidak ada yang diprediksi.")
        return
        
    # Hapus 'id' sebelum prediksi jika tidak dibutuhkan model
    features = df.drop(columns=['id'])
    
    print(f"Melakukan prediksi pada {len(features)} baris...")
    predictions = model.predict(features)
    
    # Tambahkan hasil prediksi ke DataFrame
    df['predicted_spoil'] = predictions
    
    # Siapkan data untuk diupdate
    update_data = [(row['predicted_spoil'], row['id']) for index, row in df.iterrows()]
    
    print("Mengupdate kolom 'predicted_spoil' di database...")
    update_query = f"UPDATE {SERVER_TABLE} SET predicted_spoil = %s WHERE id = %s"
    
    with server_conn.cursor() as cur:
        cur.executemany(update_query, update_data)
        server_conn.commit()
        print(f"Berhasil mengupdate {cur.rowcount} baris.")

def main():
    """Fungsi utama untuk menjalankan proses ETL."""
    print("--- Memulai Proses ETL & Prediksi ---")
    try:
        realtime_conn = get_db_connection(REALTIME_DB_CONFIG)
        server_conn = get_db_connection(SERVER_DB_CONFIG)
        
        # 1. Transfer data
        new_ids = transfer_new_data(realtime_conn, server_conn)
        
        # 2. Prediksi dan Update
        if new_ids:
            predict_and_update(server_conn, new_ids)
            
    except psycopg2.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if 'realtime_conn' in locals() and realtime_conn:
            realtime_conn.close()
        if 'server_conn' in locals() and server_conn:
            server_conn.close()
        print("--- Proses Selesai ---")

if __name__ == "__main__":
    main()
