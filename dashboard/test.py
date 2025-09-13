import psycopg2
from configparser import ConfigParser
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def config(filename, section='postgresql'):
    parser = ConfigParser()
    parser.read(filename)

    db = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            db[param[0]] = param[1]
    else:
        raise Exception(f'Section {section} not found in {filename}')
    return db

def test_connection(filename):
    try:
        full_path = os.path.join(BASE_DIR, filename)
        params = config(full_path)
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()
        print(f"✅ Connected to {filename}, PostgreSQL version: {db_version[0]}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Failed to connect {filename}: {e}")

if __name__ == "__main__":
    test_connection("realtime_db.ini")
    test_connection("server_db.ini")
