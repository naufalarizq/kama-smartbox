import psycopg2
import os
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

def insert_test_data():
    """
    Fungsi untuk memasukkan 5 baris data contoh ke tabel kama_realtime.
    """
    # Data contoh (battery, temperature, humidity, gas_level, status)
    # Termasuk status 'bad' untuk memicu logika LLM
    test_data = [
        (98.5, 25.1, 60.2, 350, 'good'),
        (95.0, 26.5, 65.8, 450, 'warning'),
        (92.3, 28.2, 70.1, 600, 'bad'),    # Data 'bad' untuk tes LLM
        (90.1, 24.8, 62.5, 380, 'good'),
        (88.7, 29.0, 75.3, 750, 'bad')     # Data 'bad' untuk tes LLM
    ]

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
