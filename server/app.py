from flask import Flask, request, jsonify
import os
import psycopg2
import sys

app = Flask(__name__)

# Configure via environment variables
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'kama')
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

    # Ambil semua field sesuai dengan tabel terbaru
    jenis_makanan = data.get('jenis_makanan', 'fruits')  # default "fruits"
    battery = data.get('battery')
    temperature = data.get('temperature')
    humidity = data.get('humidity')
    gas_level = data.get('gas_level')
    status = data.get('status')
    expired_days = data.get('expired_days')
    lid_status = data.get('lid_status', 'CLOSED')

    try:
        # Log incoming request untuk debugging
        print('Ingest from', request.remote_addr, 'payload=', data)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO kama_readings (
                jenis_makanan, battery, temperature, humidity, gas_level, status, expired_days, lid_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, recorded_at
            """,
            (jenis_makanan, battery, temperature, humidity, gas_level,
             status, expired_days, lid_status)
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
