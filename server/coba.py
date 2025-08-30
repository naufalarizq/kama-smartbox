from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- Database Config ---
DB_CONFIG = {
    "dbname": "kama",
    "user": "postgres",
    "password": "satudua3",
    "host": "localhost",  # atau ganti dengan IP server PostgreSQL kalau beda mesin
    "port": 5432
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

# --- Endpoint menerima data dari IoT ---
@app.route("/api/data", methods=["POST"])
def receive_data():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON received"}), 400

        print("📩 Data diterima dari IoT:", data)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO kama_readings (battery, temperature, humidity, gas_level, ph_level, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data.get("battery"),
            data.get("temperature"),
            data.get("humidity"),
            data.get("gas_level"),
            data.get("ph_level"),
            data.get("status")
        ))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "✅ Data saved successfully!"}), 201

    except Exception as e:
        print("⚠️ Error saat insert:", e)
        return jsonify({"error": str(e)}), 500

# --- Root endpoint ---
@app.route("/")
def index():
    return "🚀 KAMA IoT API is running"

# --- Ambil data terbaru ---
@app.route("/api/data/latest", methods=["GET"])
def latest_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM kama_readings ORDER BY recorded_at DESC LIMIT 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            return jsonify(row)
        else:
            return jsonify({"message": "No data available"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Ambil semua data (debug) ---
@app.route("/api/data/all", methods=["GET"])
def all_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM kama_readings ORDER BY recorded_at DESC LIMIT 50;")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify(rows)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # 0.0.0.0 supaya bisa diakses dari ngrok/public
    app.run(host="0.0.0.0", port=5000, debug=True)
