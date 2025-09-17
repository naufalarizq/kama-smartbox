try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2  # type: ignore
import os
import random
import requests
import joblib
import pandas as pd
from dotenv import load_dotenv

# --- Konfigurasi Koneksi Database (sama seperti di app.py) ---
# Memuat variabel dari file .env
load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'kama-realtime')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', 'satudua3')

CONN_INFO = f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={DB_PASS}"

# -----------------------------------------------------------------------------
# Mode penentuan status
#   - interactive: minta input status dari user per baris (good/warning/bad)
#   - auto: gunakan urutan (API / model lokal / acak)
#   - fixed: gunakan MANUAL_STATUS di bawah untuk semua baris
# -----------------------------------------------------------------------------
MODE = os.getenv('TEST_MODE', 'interactive').lower()  # 'interactive' | 'auto' | 'fixed'
MANUAL_STATUS = os.getenv('TEST_MANUAL_STATUS')  # digunakan jika MODE == 'fixed'

def insert_test_data():
    """
    Fungsi untuk memasukkan 5 baris data contoh ke tabel kama_realtime.
    """
    # Generate 5 baris data acak (battery, temperature, humidity, gas_level, status)
    statuses = ['good', 'warning', 'bad']
    weights = [0.6, 0.25, 0.15]  # lebih sering 'good', sedikit 'bad'
    test_data = []
    # Utility: try server API first, if unavailable fall back to local model
    MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ai/models/xgb_status_model.pkl'))

    def predict_via_api(temp, hum, gas, jenis='fruits'):
        try:
            resp = requests.post('https://kama-smartbox-production.up.railway.app/predict', json={
                'temperature': temp,
                'humidity': hum,
                'gas_level': gas,
                'jenis_makanan': jenis
            }, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('label')
        except Exception:
            return None

    def load_local_model(path):
        try:
            loaded = joblib.load(path)
            # If dict-like, try to find an object with predict
            if isinstance(loaded, dict):
                for key in ['model','models','estimator','clf']:
                    if key in loaded and hasattr(loaded[key], 'predict'):
                        return loaded[key]
                # fallback: search values
                for v in loaded.values():
                    if hasattr(v, 'predict'):
                        return v
                return None
            return loaded
        except Exception:
            return None

    def predict_local(model, temp, hum, gas, jenis='fruits'):
        try:
            X = pd.DataFrame([{'temperature': temp, 'humidity': hum, 'gas_level': gas, 'jenis_makanan': jenis}])
            pred_idx = model.predict(X)[0]
            label = None
            if hasattr(model, 'classes_'):
                label = str(model.classes_[pred_idx])
            elif hasattr(model, 'named_steps') and 'clf' in model.named_steps and hasattr(model.named_steps['clf'], 'classes_'):
                label = str(model.named_steps['clf'].classes_[pred_idx])
            if label is None or (isinstance(label, str) and label.isdigit()):
                label_map = {0: 'bad', 1: 'good', 2: 'warning'}
                try:
                    label = label_map.get(int(pred_idx), str(pred_idx))
                except Exception:
                    label = str(pred_idx)
            return label
        except Exception:
            return None

    # try loading local model once
    local_model = load_local_model(MODEL_PATH)

    # snapshot mode and manual status into local variables to avoid global reassignment issues
    mode = (MODE or 'interactive').lower()
    manual_status = (MANUAL_STATUS or '').strip().lower() if MANUAL_STATUS else None

    for i in range(1):
        battery = random.randint(80, 100)
        temperature = round(random.uniform(20.0, 30.0), 1)
        humidity = round(random.uniform(40.0, 90.0), 1)
        gas_level = round(random.uniform(200.0, 900.0), 1)

        status = None
        method = None

        if mode == 'interactive':
            # Minta input dari user, validasi, ulangi jika perlu
            while True:
                try:
                    user_in = input(f"[{i+1}/5] Masukkan status (good/warning/bad) atau kosong untuk 'good': ").strip().lower()
                except Exception:
                    user_in = ''
                if user_in == '':
                    user_in = 'good'
                if user_in in statuses:
                    status = user_in
                    method = 'user'
                    break
                else:
                    print(f"Input tidak valid. Pilihan: {statuses}")
        elif mode == 'fixed':
            if manual_status in statuses:
                status = manual_status
                method = 'manual'
            else:
                print(f"Peringatan: TEST_MANUAL_STATUS '{MANUAL_STATUS}' tidak valid. Gunakan salah satu dari {statuses}. Beralih ke mode 'auto'.")
                mode = 'auto'

        if mode == 'auto' and status is None:
            status = predict_via_api(temperature, humidity, gas_level)
            method = 'api'
            if status is None and local_model is not None:
                status = predict_local(local_model, temperature, humidity, gas_level)
                method = 'local'
            if status is None:
                status = random.choices(statuses, weights)[0]
                method = 'random'

        test_data.append((battery, temperature, humidity, gas_level, status))
        print(f"Generated row: temp={temperature}, hum={humidity}, gas={gas_level}, status={status} (via {method})")

    conn = None
    try:
        print(f"Menyambungkan ke database '{DB_NAME}'...")
        conn = psycopg2.connect(CONN_INFO)
        cur = conn.cursor()

        insert_query = """
            INSERT INTO kama_realtime (battery, temperature, humidity, gas_level, status)
            VALUES (%s, %s, %s, %s, %s);
        """

        print("Memasukkan data contoh...")
        for record in test_data:
            cur.execute(insert_query, record)
            print(f"  -> Memasukkan data: {record}")

        conn.commit()
        print(f"\nBerhasil! {len(test_data)} baris data baru telah dimasukkan ke tabel 'kama_realtime'.")
        print("Anda sekarang bisa menjalankan server utama (app.py) atau endpoint /force_run_job untuk memproses data ini.")

    except Exception as e:
        print(f"Terjadi error: {e}")
        if conn:
            conn.rollback() # Batalkan transaksi jika ada error

    finally:
        if conn:
            cur.close()
            conn.close()
            print("Koneksi database ditutup.")

if __name__ == '__main__':
    insert_test_data()
