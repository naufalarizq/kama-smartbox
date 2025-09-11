from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
from psycopg2.extras import execute_values, execute_batch
from dotenv import load_dotenv

import os
import psycopg2
import sys
import joblib
import numpy as np
from threading import Lock
# import requests # <-- Ditambahkan
import google.generativeai as genai
from datetime import datetime

app = Flask(__name__)

# --- Konfigurasi Kunci API ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    # Konfigurasi library genai secara global saat aplikasi dimulai
    genai.configure(api_key=GEMINI_API_KEY)
    print("Library Google Generative AI berhasil dikonfigurasi.")
else:
    print("PERINGATAN: GEMINI_API_KEY tidak ditemukan di environment. Fitur rekomendasi LLM akan dinonaktifkan.")

MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ai/models/xgb_status_model.pkl'))
_model = None
_model_lock = Lock()

def get_model():
    global _model
    with _model_lock:
        if _model is None:
            print('Loading model from', MODEL_PATH)
            loaded = joblib.load(MODEL_PATH)
            # If loaded is a dict, try to extract the model from known keys
            if isinstance(loaded, dict):
                # Try 'models' first, then other common keys
                for key in ['models', 'model', 'estimator', 'clf']:
                    if key in loaded:
                        candidate = loaded[key]
                        print(f"Loaded candidate from dict key: {key}, type: {type(candidate)}")
                        # If candidate is a dict, try to extract the first model inside
                        if isinstance(candidate, dict):
                            print(f"Candidate under '{key}' is a dict. Available keys: {list(candidate.keys())}")
                            found = False
                            for subkey, subval in candidate.items():
                                print(f"Type of '{subkey}': {type(subval)}")
                                if hasattr(subval, 'predict'):
                                    _model = subval
                                    print(f"Loaded model from nested dict key: {subkey}")
                                    found = True
                                    break
                            if not found:
                                raise ValueError(f"No model with 'predict' found in '{key}'. Types: {{k: str(type(v)) for k,v in candidate.items()}}")
                        else:
                            _model = candidate
                        break
                else:
                    raise ValueError(f"Model file is a dict but no known model key found. Keys: {list(loaded.keys())}")
            else:
                _model = loaded
        return _model

@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json(force=True)
    if not data:
        return jsonify({'error': 'invalid json'}), 400
    try:
        temperature = float(data.get('temperature'))
        humidity = float(data.get('humidity'))
        gas_level = float(data.get('gas_level'))
        jenis_makanan = data.get('jenis_makanan', 'fruits')  # default to 'fruits' if not provided
    except Exception as e:
        return jsonify({'error': 'missing or invalid input: %s' % e}), 400

    # Prepare input for model as DataFrame with correct column names
    import pandas as pd
    X = pd.DataFrame([{
        'temperature': temperature,
        'humidity': humidity,
        'gas_level': gas_level,
        'jenis_makanan': jenis_makanan
    }])
    model = get_model()
    # If model is a wrapper (pipeline), it will preprocess automatically
    pred_idx = model.predict(X)[0]
    # Try to get label names from model if available
    label = None
    if hasattr(model, 'classes_'):
        label = str(model.classes_[pred_idx])
    elif hasattr(model, 'named_steps') and 'clf' in model.named_steps and hasattr(model.named_steps['clf'], 'classes_'):
        label = str(model.named_steps['clf'].classes_[pred_idx])
    # fallback: use mapping if label is still None or is digit
    if label is None or label.isdigit():
        label_map = {0: "bad", 1: "good", 2: "warning"}
        label = label_map.get(int(pred_idx), str(pred_idx))
    print(f"Predict: input={X.to_dict(orient='records')} label={label}")
    return jsonify({'label': label})

# Configure via environment variables
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'kama-realtime')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASS = os.getenv('DB_PASS', 'satudua3')

CONN_INFO = f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={DB_PASS}"

print('PYTHON:', sys.executable)
print('DB CONN:', CONN_INFO)

# --- Fungsi Helper untuk LLM (Diperbarui) ---
def get_llm_recommendation(food_type: str, spoil_info: str) -> str:
    """
    Memanggil Gemini API untuk mendapatkan rekomendasi pengolahan makanan busuk.
    """
    if not GEMINI_API_KEY:
        return "Rekomendasi tidak tersedia (API Key tidak dikonfigurasi)."

    try:
        # Prompt yang lebih kontekstual
        prompt = (
            f"Makanan dengan jenis '{food_type}' telah dinyatakan busuk. {spoil_info} "
            "Berikan 2-3 ide singkat dan praktis untuk mengolahnya agar tidak menjadi sampah, "
            "misalnya dijadikan kompos atau pupuk organik cair. Jawaban harus dalam format daftar bernomor."
        )
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        
        return response.text.strip()
        
    except Exception as e:
        print(f"[LLM Error] Gagal mendapatkan rekomendasi dari AI: {e}")
        return "Gagal mendapatkan rekomendasi dari AI."

def get_conn():
    return psycopg2.connect(CONN_INFO)

@app.route('/ingest', methods=['POST'])
def ingest():
    data = request.get_json(force=True)
    if not data:
        return jsonify({'error': 'invalid json'}), 400

    # Ambil field untuk kama_realtime
    battery = data.get('battery')
    temperature = data.get('temperature')
    humidity = data.get('humidity')
    gas_level = data.get('gas_level')
    status = data.get('status')

    try:
        # Log incoming request untuk debugging
        print('Ingest from', request.remote_addr, 'payload=', data)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO kama_realtime (
                battery, temperature, humidity, gas_level, status
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, recorded_at
            """,
            (battery, temperature, humidity, gas_level, status)
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        print('Inserted id=', row[0])
        return jsonify({'ok': True, 'id': row[0], 'recorded_at': row[1].isoformat()}), 201
    except Exception as e:
        print('Ingest error:', e)
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return 'KAMA receiver running. Use /ingest (POST) or /health (GET).'

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

# --- Endpoint baru untuk Dashboard ---
# Konfigurasi untuk database kama_server
SERVER_DB_CONFIG = {
    "host": os.getenv("SERVER_DB_HOST", "localhost"),
    "port": int(os.getenv("SERVER_DB_PORT", 5432)),
    "dbname": os.getenv("SERVER_DB_NAME", "kama-server"),
    "user": os.getenv("SERVER_DB_USER", "postgres"),
    "password": os.getenv("SERVER_DB_PASS", "satudua3"),
}

# --- Logic untuk Scheduled Job (dari process_spoil_prediction.py) ---

SPOIL_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ai/models/xgb_predicted_spoiled.pkl'))
_spoil_model = None
_spoil_model_lock = Lock()

def get_spoil_model():
    """Memuat model untuk prediksi kebusukan (predicted_spoil)."""
    global _spoil_model
    with _spoil_model_lock:
        if _spoil_model is None:
            print(f"[Scheduler] Memuat model dari {SPOIL_MODEL_PATH}...")
            loaded_obj = joblib.load(SPOIL_MODEL_PATH)
            if isinstance(loaded_obj, dict):
                for key in ['model', 'estimator', 'predictor', 'xgb']:
                    if key in loaded_obj and hasattr(loaded_obj[key], 'predict'):
                        _spoil_model = loaded_obj[key]
                        print(f"[Scheduler] Model ditemukan dalam kunci: '{key}'")
                        break
                else:
                    raise ValueError(f"Tidak dapat menemukan objek model yang valid di dalam dictionary. Kunci: {list(loaded_obj.keys())}")
            else:
                _spoil_model = loaded_obj
        return _spoil_model

def run_spoil_prediction_job():
    """
    Fungsi yang dijalankan scheduler untuk transfer data dan prediksi.
    """
    print("--- [Scheduler] Memulai Proses ETL & Prediksi ---")
    realtime_conn = None
    server_conn = None
    try:
        realtime_conn = get_conn()
        server_conn = get_server_db_connection()

        # 1. Transfer data baru
        with server_conn.cursor() as server_cur:
            server_cur.execute("SELECT MAX(recorded_at) FROM kama_server")
            last_timestamp = server_cur.fetchone()[0]

        with realtime_conn.cursor() as realtime_cur:
            if last_timestamp:
                realtime_cur.execute(
                    "SELECT id, battery, temperature, humidity, gas_level, status, recorded_at FROM kama_realtime WHERE recorded_at > %s",
                    (last_timestamp,)
                )
            else:
                realtime_cur.execute(
                    "SELECT id, battery, temperature, humidity, gas_level, status, recorded_at FROM kama_realtime"
                )
            new_data = realtime_cur.fetchall()

        if not new_data:
            print("[Scheduler] Tidak ada data baru untuk ditransfer.")
            # Penting: Tutup koneksi sebelum keluar dari fungsi
            if realtime_conn: realtime_conn.close()
            if server_conn: server_conn.close()
            print("--- [Scheduler] Proses Selesai (tidak ada data) ---")
            return

        print(f"[Scheduler] Ditemukan {len(new_data)} baris data baru untuk ditransfer.")
        insert_query = """
            INSERT INTO kama_server (id, battery, temperature, humidity, gas_level, status, recorded_at)
            VALUES %s ON CONFLICT (id) DO NOTHING RETURNING id;
        """
        with server_conn.cursor() as server_cur_insert:
            inserted_ids_tuples = execute_values(server_cur_insert, insert_query, new_data, fetch=True)
            server_conn.commit()
            new_ids = [item[0] for item in inserted_ids_tuples]
        
        if not new_ids:
            print("[Scheduler] Tidak ada baris baru yang berhasil dimasukkan (kemungkinan data duplikat).")
            # Penting: Tutup koneksi sebelum keluar dari fungsi
            if realtime_conn: realtime_conn.close()
            if server_conn: server_conn.close()
            print("--- [Scheduler] Proses Selesai (data duplikat) ---")
            return

        # 2. Ambil data yang baru dimasukkan untuk prediksi dan rekomendasi
        print(f"[Scheduler] Mengambil {len(new_ids)} baris baru dari kama_server untuk diproses.")
        # Hanya proses baris paling terakhir yang ditransfer pada run ini
        with server_conn.cursor() as server_cur_select:
            # Menggunakan tuple untuk klausa IN, lalu ambil yang paling akhir berdasarkan recorded_at
            server_cur_select.execute(
                "SELECT id, temperature, humidity, gas_level, status, jenis_makanan FROM kama_server WHERE id IN %s ORDER BY recorded_at DESC LIMIT 1",
                (tuple(new_ids),)
            )
            rows_to_process = server_cur_select.fetchall()

        # 3. Lakukan prediksi, panggil LLM jika perlu, dan siapkan update
        print(f"[Scheduler] Jumlah baris yang akan diproses untuk prediksi/LLM: {len(rows_to_process)}")
        spoil_model = get_spoil_model()

        # Buat DataFrame untuk kemudahan prediksi
        df_to_predict = pd.DataFrame(rows_to_process, columns=['id', 'temperature', 'humidity', 'gas_level', 'status', 'jenis_makanan'])

        # Pastikan kolom yang dibutuhkan model ada
        features = ['temperature', 'humidity', 'gas_level', 'jenis_makanan']
        X_predict = df_to_predict[features]

        print(f"[Scheduler] Melakukan prediksi 'predicted_spoil' untuk {len(X_predict)} baris.")
        predictions = spoil_model.predict(X_predict)
        df_to_predict['predicted_spoil'] = predictions

        print("[Scheduler] Memproses hasil dan menyiapkan update database...")
        update_query = "UPDATE kama_server SET predicted_spoil = %s, recommendation_text = %s WHERE id = %s"
        update_data = []

        for index, row in df_to_predict.iterrows():
            recommendation = None # Default
            # Periksa jika status adalah 'bad'
            if row['status'] == 'bad':
                print(f"[Scheduler] Status 'bad' terdeteksi untuk id: {row['id']}. Memanggil LLM...")
                spoil_info = f"Prediksi waktu busuk adalah {row['predicted_spoil']:.2f} hari."
                # Default 'fruits' jika jenis_makanan adalah None atau kosong
                food_type = row['jenis_makanan'] if row['jenis_makanan'] else 'buah-buahan'

                recommendation = get_llm_recommendation(food_type, spoil_info)
                print(f"[Scheduler] Rekomendasi diterima untuk id: {row['id']}.")

            update_data.append((row['predicted_spoil'], recommendation, row['id']))

        # 4. Lakukan update batch ke database
        if update_data:
            print(f"[Scheduler] Melakukan batch update untuk {len(update_data)} baris.")
            with server_conn.cursor() as server_cur_update:
                execute_batch(server_cur_update, update_query, update_data)
                server_conn.commit()
            print("[Scheduler] Batch update berhasil.")

        print("[Scheduler] Semua proses untuk data baru telah selesai.")

    except Exception as e:
        print(f"[Scheduler] Terjadi error pada job: {e}")
    finally:
        # Blok finally ini sekarang lebih aman
        if realtime_conn:
            realtime_conn.close()
        if server_conn:
            server_conn.close()
        print("--- [Scheduler] Proses Selesai (koneksi ditutup) ---")


def get_server_db_connection():
    """Membuat koneksi ke database kama_server."""
    return psycopg2.connect(**SERVER_DB_CONFIG)

@app.route('/latest_spoil_prediction', methods=['GET'])
def latest_spoil_prediction():
    """
    Mengambil nilai predicted_spoil terbaru dari database kama_server.
    Endpoint ini ditujukan untuk dashboard.
    """
    try:
        conn = get_server_db_connection()
        cur = conn.cursor()
        
        # Ambil baris terbaru berdasarkan recorded_at
        cur.execute(
            """
            SELECT predicted_spoil, recorded_at 
            FROM kama_server 
            WHERE predicted_spoil IS NOT NULL
            ORDER BY recorded_at DESC 
            LIMIT 1
            """
        )
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            prediction, timestamp = result
            return jsonify({
                'latest_predicted_spoil': prediction,
                'recorded_at': timestamp.isoformat()
            })
        else:
            # Kasus jika tabel kosong atau belum ada prediksi
            return jsonify({
                'latest_predicted_spoil': None,
                'message': 'No prediction data found.'
            }), 404
            
    except Exception as e:
        print(f"Error fetching latest spoil prediction: {e}")
        return jsonify({'error': str(e)}), 500

# --- Endpoint Debug Sementara ---
@app.route('/force_run_job', methods=['GET'])
def force_run_job():
    """
    Endpoint ini hanya untuk testing.
    Memaksa scheduler job untuk berjalan sekali saja.
    """
    print("\n!!! Memicu job secara manual via endpoint /force_run_job !!!\n")
    run_spoil_prediction_job()
    return jsonify({'status': 'ok', 'message': 'Job prediksi kebusukan telah dipicu. Periksa log di terminal.'})

if __name__ == '__main__':
    # Konfigurasi dan jalankan scheduler
    scheduler = BackgroundScheduler(daemon=True)
    
    # PERBAIKAN UTAMA: Gunakan 'next_run_time' untuk menjalankan job saat startup
    scheduler.add_job(
        run_spoil_prediction_job, 
        'interval', 
        hours=1, 
        next_run_time=datetime.now()
    )
    
    scheduler.start()
    print("Scheduler internal telah dimulai.")
    print("Job pertama akan langsung dijalankan, lalu berulang setiap 1 jam.")
    
    # Jalankan aplikasi Flask
    app.run(host='0.0.0.0', port=5000)
