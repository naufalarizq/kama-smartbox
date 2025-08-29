import machine
import time
import dht

# --- Hardware Pin Configuration ---
# LEDs
green_led = machine.Pin(13, machine.Pin.OUT)
yellow_led = machine.Pin(12, machine.Pin.OUT)
red_led = machine.Pin(14, machine.Pin.OUT)

# Sensors
dht_sensor = dht.DHT22(machine.Pin(27))
reed_switch = machine.Pin(26, machine.Pin.IN, machine.Pin.PULL_UP)

# Analog Sensors (ADC - Analog to Digital Converter)
# Configure ADC for full 0-3.3V range
gas_adc = machine.ADC(machine.Pin(34))
gas_adc.atten(machine.ADC.ATTN_11DB)
ph_adc = machine.ADC(machine.Pin(35))
ph_adc.atten(machine.ADC.ATTN_11DB)

# NEW: ADC for the Battery level simulation connected to GPIO 32
battery_adc = machine.ADC(machine.Pin(32))
battery_adc.atten(machine.ADC.ATTN_11DB)

# --- Helper Functions ---
def map_value(x, in_min, in_max, out_min, out_max):
    """Maps a value from one range to another."""
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def set_led_status(status):
    """Controls the LEDs based on the food status."""
    green_led.off()
    yellow_led.off()
    red_led.off()

    if status == 'good':
        green_led.on()
    elif status == 'warning':
        yellow_led.on()
    elif status == 'bad':
        red_led.on()

# --- Main Program Loop ---
print("Food Analysis Box - Initializing...")
time.sleep(2)

while True:
    try:
        # --- 0. System Checks (Battery and Lid) ---

        # Read and map the battery level first
        battery_raw = battery_adc.read()
        battery_level = map_value(battery_raw, 0, 4095, 0, 100)

        # If battery is low, it's a critical system warning
        if battery_level < 20:
            print(f"!!! CRITICAL: LOW BATTERY ({battery_level:.0f}%) !!!")
            # Blink red LED to indicate system failure, overriding food status
            red_led.on()
            time.sleep(0.5)
            red_led.off()
            time.sleep(0.5)
            continue # Skip normal operation

        # Check if the lid is closed. Reed switch is 0 when magnet is near (closed).
        if reed_switch.value() == 1:
            print("Box lid is OPEN. Pausing analysis.")
            set_led_status('off') # Turn all LEDs off
            time.sleep(1)
            continue # Skip the rest of the loop until the lid is closed

        # --- 1. Read Food Sensor Data ---
        dht_sensor.measure()
        temp = dht_sensor.temperature()
        humidity = dht_sensor.humidity()
        gas_raw = gas_adc.read()
        ph_raw = ph_adc.read()

        # --- 2. Process and Map Data ---
        gas_level = map_value(gas_raw, 0, 4095, 0, 100)
        ph_level = map_value(ph_raw, 0, 4095, 0, 14)

        # --- 3. Analyze Food Condition ---
        # These thresholds define what is considered good, warning, or bad.
        status = 'good' # Assume good by default

        # Bad conditions (triggers red light immediately)
        if temp > 35 or gas_level > 60 or ph_level < 4.0 or ph_level > 9.5:
            status = 'bad'
        # Warning conditions (triggers yellow light if not already bad)
        elif temp > 30 or humidity > 85 or gas_level > 40 or ph_level < 5.0 or ph_level > 8.5:
            status = 'warning'

        # --- 4. Update LED and Print Status ---
        set_led_status(status)
        
        print("--------------------------------")
        print(f"Lid Status:   CLOSED")
        print(f"Battery:      {battery_level:.0f}%")
        print(f"Temperature:  {temp}°C")
        print(f"Humidity:     {humidity}%")
        print(f"Gas Level:    {gas_level:.1f}%")
        print(f"pH Level:     {ph_level:.2f}")
        print(f"CONDITION:    {status.upper()}")
        print("--------------------------------\n")

    except OSError as e:
        print("Failed to read sensor:", e)
        set_led_status('bad')

    # Wait for 3 seconds before the next reading
    time.sleep(3)