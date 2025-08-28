Flask receiver for KAMA IoT readings

1. Create a Postgres database and run the SQL in `../database/Scripts/Script.sql` to create the `kama_readings` table.

2. Configure environment variables (optionally):

- DB_HOST (default: localhost)
- DB_PORT (default: 5432)
- DB_NAME (default: kama)
- DB_USER (default: postgres)
- DB_PASS (default: empty)

3. Install dependencies and run:

# Windows PowerShell example

python -m venv .venv; .\.venv\Scripts\Activate; pip install -r requirements.txt; python app.py

4. Configure `SERVER_URL` in the MicroPython `main.py` to point to this server, e.g. `http://192.168.1.100:5000/ingest`.

Notes:

- In Wokwi, the ESP32 must be on the same network and able to reach the server IP (or you can expose the server using ngrok or similar).
- For local testing, you can run the Flask app and then use `curl` or Postman to POST JSON to `/ingest`.
