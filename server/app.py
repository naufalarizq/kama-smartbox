
from flask import Flask, request, jsonify

import os
import psycopg2
import sys
import joblib
import numpy as np
from threading import Lock

app = Flask(__name__)

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

if __name__ == '__main__':
    # For local dev
    app.run(host='0.0.0.0', port=5000)
