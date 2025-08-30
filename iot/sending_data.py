import requests
import random
import time

SERVER_URL = "http://localhost:5000/ingest"

def determine_status(temp, hum, gas, ph):
    """
    Tentukan status dan expired berdasarkan kondisi lingkungan.
    """
    # Default
    status = "good"
    expired_days = 7
    

    # Kondisi busuk total
    if temp > 35 or hum > 90 or gas > 80 or ph < 4.0 or ph > 8.5:
        status = "bad"
        expired_days = 0

    # Kondisi warning
    elif temp > 30 or hum > 85 or gas > 50 or ph < 4.5 or ph > 8.0:
        status = "warning"
        expired_days = random.randint(1, 3)

    # Kondisi good
    else:
        status = "good"
        expired_days = random.randint(5, 10)

    return status, expired_days


while True:
    # Sensor dummy
    battery = random.randint(30, 100)
    temp = round(random.uniform(20.0, 40.0), 2)
    hum = round(random.uniform(40.0, 95.0), 2)
    gas = round(random.uniform(0, 100), 2)
    ph = round(random.uniform(3.0, 9.0), 2)

    # Tentukan status & expired otomatis
    status, expired_in_days = determine_status(temp, hum, gas, ph)

    data = {
        "battery": battery,
        "temperature": temp,
        "humidity": hum,
        "gas_level": gas,
        "ph_level": ph,
        "status": status,
        "box_status": random.choice(["terbuka", "tertutup"]),
        "expired_in_days": expired_in_days
    }

    try:
        res = requests.post(SERVER_URL, json=data)
        print("Sent:", data)
        print("Response:", res.status_code, res.text)
    except Exception as e:
        print("⚠️ Error sending data:", e)

    time.sleep(5)
