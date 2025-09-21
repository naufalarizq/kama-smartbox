from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import pandas as pd
import os
import sys
import joblib
import numpy as np
from threading import Lock
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv
import traceback

try:
    import psycopg2
    from psycopg2.extras import execute_values, execute_batch
except ModuleNotFoundError:
    import psycopg as psycopg2
    from psycopg.extras import execute_values, execute_batch

app = Flask(__name__)

# --- Konfigurasi Kunci API dan Variabel Lingkungan ---
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print("Library Google Generative AI berhasil dikonfigurasi.")
else:
    print("PERINGATAN: GEMINI_API_KEY tidak ditemukan. Fitur rekomendasi LLM akan dinonaktifkan.")

# --- Konfigurasi Koneksi Database ---
DB_HOST = os.getenv("SERVER_DB_HOST") or os.getenv("REALTIME_DB_HOST")
DB_PORT = os.getenv("SERVER_DB_PORT") or os.getenv("REALTIME_DB_PORT")
DB_USER = os.getenv("SERVER_DB_USER") or os.getenv("REALTIME_DB_USER")
DB_PASS = os.getenv("SERVER_DB_PASS") or os.getenv("REALTIME_DB_PASS")
DB_NAME = os.getenv("SERVER_DB_NAME") or os.getenv("REALTIME_DB_NAME")

try:
    DB_PORT = int(DB_PORT)
except (ValueError, TypeError):
    DB_PORT = 5432

_masked_pass = '***' if DB_PASS else ''
print(f"PYTHON: {sys.executable}")
print(f"DB CONN CONFIG: host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={_masked_pass}")

def get_conn():
    """Membuat koneksi ke database menggunakan variabel lingkungan yang dimuat."""
    try:
        conn_kwargs = {
            'host': DB_HOST,
            'port': DB_PORT,
            'dbname': DB_NAME,
            'user': DB_USER,
            'password': DB_PASS,
            'sslmode': 'require'
        }
        conn_kwargs = {k: v for k, v in conn_kwargs.items() if v is not None}
        return psycopg2.connect(**conn_kwargs)
    except Exception as e:
        print(f"[get_conn] Koneksi gagal: {e}")
        raise

# --- Fungsi Model Prediksi Status Makanan ---
MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ai/models/xgb_status_model.pkl'))
_model = None
_model_lock = Lock()

def get_model():
    global _model
    with _model_lock:
        if _model is None:
            print('Loading model from', MODEL_PATH)
            loaded = joblib.load(MODEL_PATH)
            if isinstance(loaded, dict):
                for key in ['models', 'model', 'estimator', 'clf']:
                    if key in loaded:
                        candidate = loaded[key]
                        if isinstance(candidate, dict):
                            found = False
                            for subkey, subval in candidate.items():
                                if hasattr(subval, 'predict'):
                                    _model = subval
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

# --- Endpoint untuk prediksi status makanan ---
@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json(force=True)
    if not data:
        return jsonify({'error': 'invalid json'}), 400
    try:
        temperature = float(data.get('temperature'))
        humidity = float(data.get('humidity'))
        gas_level = float(data.get('gas_level'))
        jenis_makanan = data.get('jenis_makanan', 'fruits')
    except Exception as e:
        return jsonify({'error': f'missing or invalid input: {e}'}), 400

    X = pd.DataFrame([{
        'temperature': temperature,
        'humidity': humidity,
        'gas_level': gas_level,
        'jenis_makanan': jenis_makanan
    }])
    model = get_model()
    pred_idx = model.predict(X)[0]
    label = None
    if hasattr(model, 'classes_'):
        label = str(model.classes_[pred_idx])
    elif hasattr(model, 'named_steps') and 'clf' in model.named_steps and hasattr(model.named_steps['clf'], 'classes_'):
        label = str(model.named_steps['clf'].classes_[pred_idx])
    if label is None or label.isdigit():
        label_map = {0: "bad", 1: "good", 2: "warning"}
        label = label_map.get(int(pred_idx), str(pred_idx))
    print(f"Predict: input={X.to_dict(orient='records')} label={label}")
    return jsonify({'label': label})

# --- Fungsi Helper untuk LLM ---
def get_llm_recommendation(food_type: str, spoil_info: str) -> str:
    if not GEMINI_API_KEY:
        return "Rekomendasi tidak tersedia (API Key tidak dikonfigurasi)."
    try:
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

# --- Endpoint untuk ESP32: Ingest Data ---
@app.route('/ingest', methods=['POST'])
def ingest():
    data = request.get_json(force=True)
    if not data:
        return jsonify({'error': 'invalid json'}), 400
    battery = data.get('battery')
    temperature = data.get('temperature')
    humidity = data.get('humidity')
    gas_level = data.get('gas_level')
    status = data.get('status')
    try:
        print('Ingest from', request.remote_addr, 'payload=', data)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO kama_realtime (battery, temperature, humidity, gas_level, status) VALUES (%s, %s, %s, %s, %s) RETURNING id, recorded_at",
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

@app.route('/latest_status', methods=['GET'])
def latest_status():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT status, recorded_at FROM kama_realtime ORDER BY recorded_at DESC LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return jsonify({'status': None, 'recorded_at': None, 'message': 'No data available'}), 404
        return jsonify({'status': row[0], 'recorded_at': row[1].isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Logic untuk Scheduled Job ---
SPOIL_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ai/models/xgb_predicted_spoiled.pkl'))
_spoil_model = None
_spoil_model_lock = Lock()

def get_spoil_model():
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
    print("--- [Scheduler] Memulai Proses ETL & Prediksi ---")
    realtime_conn = None
    server_conn = None
    try:
        realtime_conn = get_conn()
        server_conn = get_conn()

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
            return

        print(f"[Scheduler] Ditemukan {len(new_data)} baris data baru untuk ditransfer.")
        insert_query = "INSERT INTO kama_server (id, battery, temperature, humidity, gas_level, status, recorded_at) VALUES %s ON CONFLICT (id) DO NOTHING RETURNING id;"
        
        with server_conn.cursor() as server_cur_insert:
            inserted_ids_tuples = execute_values(server_cur_insert, insert_query, new_data, fetch=True)
            server_conn.commit()
            new_ids = [item[0] for item in inserted_ids_tuples]
        
        if not new_ids:
            print("[Scheduler] Tidak ada baris baru yang berhasil dimasukkan (kemungkinan data duplikat).")
            return
            
        print("[Scheduler] Mengambil baris data terbaru untuk diproses.")
        # Hanya ambil satu baris terakhir yang baru saja dimasukkan
        with server_conn.cursor() as server_cur_select:
            server_cur_select.execute(
                "SELECT id, temperature, humidity, gas_level, status, jenis_makanan FROM kama_server WHERE id = ANY(%s) ORDER BY recorded_at DESC LIMIT 1",
                (new_ids,) 
            )
            rows_to_process = server_cur_select.fetchall()

        print(f"[Scheduler] Jumlah baris yang akan diproses untuk prediksi/LLM: {len(rows_to_process)}")
        spoil_model = get_spoil_model()

        df_to_predict = pd.DataFrame(rows_to_process, columns=['id', 'temperature', 'humidity', 'gas_level', 'status', 'jenis_makanan'])
        features = ['temperature', 'humidity', 'gas_level', 'jenis_makanan']
        X_predict = df_to_predict[features]

        print(f"[Scheduler] Melakukan prediksi 'predicted_spoil' untuk {len(X_predict)} baris.")
        predictions = spoil_model.predict(X_predict)
        df_to_predict['predicted_spoil'] = predictions

        print("[Scheduler] Memproses hasil dan menyiapkan update database...")
        update_query = "UPDATE kama_server SET predicted_spoil = %s, recommendation_text = %s WHERE id = %s"
        update_data = []

        for index, row in df_to_predict.iterrows():
            recommendation = None
            if row['status'] == 'bad':
                print(f"[Scheduler] Status 'bad' terdeteksi untuk id: {row['id']}. Memanggil LLM...")
                spoil_info = f"Prediksi waktu busuk adalah {row['predicted_spoil']:.2f} hari."
                food_type = row['jenis_makanan'] or 'buah-buahan' # Menggunakan 'or' untuk mengatasi None/kosong
                recommendation = get_llm_recommendation(food_type, spoil_info)
                print(f"[Scheduler] Rekomendasi diterima untuk id: {row['id']}.")
            update_data.append((row['predicted_spoil'], recommendation, row['id']))

        if update_data:
            print(f"[Scheduler] Melakukan batch update untuk {len(update_data)} baris.")
            with server_conn.cursor() as server_cur_update:
                execute_batch(server_cur_update, update_query, update_data)
                server_conn.commit()
            print("[Scheduler] Batch update berhasil.")
        print("[Scheduler] Semua proses untuk data baru telah selesai.")

    except Exception as e:
        print(f"[Scheduler] Terjadi error pada job: {e}")
        traceback.print_exc()
    finally:
        if realtime_conn:
            realtime_conn.close()
        if server_conn:
            server_conn.close()
        print("--- [Scheduler] Proses Selesai (koneksi ditutup) ---")

@app.route('/latest_spoil_prediction', methods=['GET'])
def latest_spoil_prediction():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM kama_server
            WHERE predicted_spoil IS NOT NULL OR recommendation_text IS NOT NULL
            ORDER BY recorded_at DESC
            LIMIT 1
            """
        )
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result:
            # Dapatkan nama kolom dari kursor untuk membuat kamus (dictionary)
            columns = [desc[0] for desc in cur.description]
            data = dict(zip(columns, result))
            
            # Ubah data menjadi format JSON yang lebih rapi
            if isinstance(data.get('recorded_at'), datetime):
                data['recorded_at'] = data['recorded_at'].isoformat()
            
            return jsonify(data)
        else:
            return jsonify({
                'message': 'No prediction data found.'
            }), 404
    except Exception as e:
        print(f"Error fetching latest spoil prediction: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/force_run_job', methods=['GET'])
def force_run_job():
    print("\n!!! Memicu job secara manual via endpoint /force_run_job !!!\n")
    run_spoil_prediction_job()
    return jsonify({'status': 'ok', 'message': 'Job prediksi kebusukan telah dipicu. Periksa log di terminal.'})

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(
    run_spoil_prediction_job,
    'interval',
    minutes=5,
    next_run_time=datetime.now()
)
scheduler.start()
print("Scheduler internal telah dimulai.")
print("Job pertama akan langsung dijalankan, lalu berulang setiap 5 menit.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)