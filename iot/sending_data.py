import requests
import random
import time

SERVER_URL = "http://localhost:5000/ingest"

def calculate_expired_days(temp, hum, gas, status):
    """
    Hitung expired days menggunakan formula regresi linear.
    Jika status = 'bad' maka expired_days = 0.
    """
    # If clearly bad, treat as already expired
    if status == "bad":
        return 0

    # Regression coefficients obtained from Dataset.csv (OLS):
    # intercept = 8.63405920
    # coef_temp  = 0.10805081
    # coef_hum   = -0.0446278961
    # coef_co2   = -0.00463152026
    # Note: model R2 ~= 0.0107 (very low) — predictions are noisy; use as rough estimate only.
    intercept = 8.63405920
    coef_temp = 0.10805081
    coef_hum = -0.0446278961
    coef_co2 = -0.00463152026

    days = intercept + (coef_temp * temp) + (coef_hum * hum) + (coef_co2 * gas)
    # Clamp and round
    days = max(0.0, days)
    return round(days, 2)


def determine_status(temp, hum, gas):
    """
    Tentukan status makanan berdasarkan threshold dari boxplot.
    Status: good, warning, bad
    """
    # Use dataset statistics to set thresholds (based on provided percentiles and medians):
    # - Temp: p75=24, p90=26
    # - Hum : p75=68, p90=71
    # - CO2 : p75=404, p90=410
    # We'll treat values above p90 as 'bad', above p75 as 'warning'.
    status = "good"

    # Hard 'bad' thresholds (p90 or clearly dangerous)
    if temp >= 26 or hum >= 72 or gas >= 410:
        return "bad"

    # Warning thresholds (between p75 and p90)
    if temp > 24 or hum > 68 or gas > 404:
        # If one metric crosses warning boundary, mark warning.
        # But if two metrics are moderately high, escalate to warning as well.
        return "warning"

    # Combination check: two moderate signals -> warning
    moderate_count = 0
    if temp > 23:
        moderate_count += 1
    if hum > 65:
        moderate_count += 1
    if gas > 402:
        moderate_count += 1
    if moderate_count >= 2:
        return "warning"

    return status


while True:
    # Sensor dummy (acak sesuai rentang boxplot)
    battery = random.randint(30, 100)
    temp = round(random.uniform(18, 30), 2)
    hum = round(random.uniform(40, 95), 2)
    gas = round(random.uniform(395, 420), 2)

    # Tentukan status
    status = determine_status(temp, hum, gas)

    # Hitung expired days dengan formula
    expired_days = calculate_expired_days(temp, hum, gas, status)

    data = {
        "jenis_makanan": "fruits",   # kolom baru sesuai tabel
        "battery": battery,
        "temperature": temp,
        "humidity": hum,
        "gas_level": gas,
        "status": status,
        "expired_days": expired_days,
        "lid_status": random.choice(["OPEN", "CLOSED"])
    }

    try:
        res = requests.post(SERVER_URL, json=data)
        print("Sent:", data)
        print("Response:", res.status_code, res.text)
    except Exception as e:
        print("⚠️ Error sending data:", e)

    time.sleep(3)
