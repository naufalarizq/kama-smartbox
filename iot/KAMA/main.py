import machine
import time
import dht

# Networking + HTTP for MicroPython (Wokwi/ESP32)
try:
    import network
    import urequests as requests
    import ujson as json
except Exception:
    import requests, json

# --- WiFi Config ---
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASS = ""

# --- Server Config ---
SERVER_URL = " https://a02eb7262646.ngrok-free.app"  # Ganti dgn IP server kamu

# --- Hardware Pin Configuration ---
green_led = machine.Pin(13, machine.Pin.OUT)
yellow_led = machine.Pin(12, machine.Pin.OUT)
red_led = machine.Pin(14, machine.Pin.OUT)

dht_sensor = dht.DHT22(machine.Pin(27))
reed_switch = machine.Pin(26, machine.Pin.IN, machine.Pin.PULL_UP)

gas_adc = machine.ADC(machine.Pin(34))
gas_adc.atten(machine.ADC.ATTN_11DB)
ph_adc = machine.ADC(machine.Pin(35))
ph_adc.atten(machine.ADC.ATTN_11DB)
battery_adc = machine.ADC(machine.Pin(32))
battery_adc.atten(machine.ADC.ATTN_11DB)

# --- Helper Functions ---
def map_value(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def set_led_status(status):
    green_led.off()
    yellow_led.off()
    red_led.off()
    if status == 'good':
        green_led.on()
    elif status == 'warning':
        yellow_led.on()
    elif status == 'bad':
        red_led.on()

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    print("Connecting to WiFi...", end="")
    while not wlan.isconnected():
        print(".", end="")
        time.sleep(0.5)
    print("\nConnected! IP:", wlan.ifconfig()[0])
    return wlan

# --- Main Program ---
print("Food Analysis Box - Initializing...")
time.sleep(2)

try:
    wifi = connect_wifi()
except:
    print("⚠️ Failed to connect WiFi!")

while True:
    try:
        # Battery
        battery_raw = battery_adc.read()
        battery_level = map_value(battery_raw, 0, 4095, 0, 100)

        if battery_level < 20:
            print(f"!!! CRITICAL: LOW BATTERY ({battery_level:.0f}%) !!!")
            red_led.on()
            time.sleep(0.5)
            red_led.off()
            time.sleep(0.5)
            continue

        # Lid check
        if reed_switch.value() == 1:
            print("Box lid is OPEN. Pausing analysis.")
            set_led_status('off')
            time.sleep(1)
            continue

        # Read sensors
        dht_sensor.measure()
        temp = dht_sensor.temperature()
        humidity = dht_sensor.humidity()
        gas_raw = gas_adc.read()
        ph_raw = ph_adc.read()

        gas_level = map_value(gas_raw, 0, 4095, 0, 100)
        ph_level = map_value(ph_raw, 0, 4095, 0, 14)

        # Food status
        status = "good"
        if temp > 35 or gas_level > 60 or ph_level < 4.0 or ph_level > 9.5:
            status = "bad"
        elif temp > 30 or humidity > 85 or gas_level > 40 or ph_level < 5.0 or ph_level > 8.5:
            status = "warning"

        set_led_status(status)

        # JSON sesuai DB
        data = {
            "battery": int(battery_level),
            "temperature": float(temp),
            "humidity": float(humidity),
            "gas_level": float(gas_level),
            "ph_level": float(ph_level),
            "status": status
        }

        print("Sending data:", data)

        try:
            res = requests.post(SERVER_URL, json=data)
            print("Server response:", res.text)
            res.close()
        except Exception as e:
            print("⚠️ Failed to send data:", e)

    except OSError as e:
        print("Failed to read sensor:", e)
        set_led_status('bad')

    time.sleep(3)
