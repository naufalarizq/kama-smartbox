#include "DHT.h"

// Pin definitions
#define DHT_PIN 4
#define MQ135_PIN 34
#define RED_LED 25
#define YELLOW_LED 26
#define GREEN_LED 27

// Sensor setup
#define DHT_TYPE DHT22
DHT dht(DHT_PIN, DHT_TYPE);

// Thresholds
const float TEMP_MIN = 2.0;   // Min safe temp (°C)
const float TEMP_MAX = 8.0;   // Max safe temp (°C)
const float HUMID_MIN = 40.0; // Min safe humidity (%)
const float HUMID_MAX = 70.0; // Max safe humidity (%)
const int GAS_THRESHOLD = 400; // Gas danger level

// Timing
unsigned long lastReading = 0;
unsigned long lastDetailedLog = 0;
const unsigned long READING_INTERVAL = 2000; // 2 seconds
const unsigned long LOG_INTERVAL = 10000;    // 10 seconds detailed log

// Variables
float temperature, humidity;
int gasLevel;
String foodStatus;

void setup() {
  Serial.begin(115200);  // Faster baud rate for more data
  delay(1500);
  
  // Initialize sensors
  dht.begin();
  
  // Initialize LEDs
  pinMode(RED_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  
  // Turn off all LEDs
  turnOffAllLEDs();
  
  Serial.println("=== KAMA Food Safety Monitor ===");
  Serial.println("Starting sensor readings...");
  Serial.println();
  printHeader();
}

void loop() {
  if (millis() - lastReading >= READING_INTERVAL) {
    readSensors();
    evaluateFoodSafety();
    printCurrentValues();
    lastReading = millis();
  }
  
  // Detailed log every 10 seconds
  if (millis() - lastDetailedLog >= LOG_INTERVAL) {
    printDetailedLog();
    lastDetailedLog = millis();
  }
}

void readSensors() {
  // Read DHT22
  temperature = dht.readTemperature();
  humidity = dht.readHumidity();
  
  // Read MQ-135 (0-4095 range for ESP32)
  gasLevel = analogRead(MQ135_PIN);
  
  // Validate readings
  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("❌ DHT22 reading error!");
    return;
  }
}

void printHeader() {
  Serial.println("Time(s) | Temp(°C) | Humid(%) | Gas Level | Status");
  Serial.println("--------|----------|----------|-----------|--------");
}

void printCurrentValues() {
  // Format: Time | Temperature | Humidity | Gas Level | Status
  Serial.print(millis()/1000);
  Serial.print("s     | ");
  
  Serial.print(temperature, 1);
  Serial.print("°C    | ");
  
  Serial.print(humidity, 1);
  Serial.print("%     | ");
  
  Serial.print(gasLevel);
  Serial.print("       | ");
  
  Serial.println(getCurrentStatus());
}

void printDetailedLog() {
  Serial.println();
  Serial.println("=== DETAILED SENSOR REPORT ===");
  Serial.print("📊 Temperature: "); 
  Serial.print(temperature, 2); 
  Serial.print("°C (Safe range: "); 
  Serial.print(TEMP_MIN); Serial.print("-"); Serial.print(TEMP_MAX); Serial.println("°C)");
  
  Serial.print("💧 Humidity: "); 
  Serial.print(humidity, 2); 
  Serial.print("% (Safe range: "); 
  Serial.print(HUMID_MIN); Serial.print("-"); Serial.print(HUMID_MAX); Serial.println("%)");
  
  Serial.print("🌫️  Gas Level: "); 
  Serial.print(gasLevel); 
  Serial.print(" (Threshold: <"); 
  Serial.print(GAS_THRESHOLD); Serial.println(")");
  
  Serial.print("🍎 Food Status: "); 
  Serial.println(foodStatus);
  
  // Show individual checks
  Serial.println("--- Safety Checks ---");
  Serial.print("Temperature OK: "); Serial.println((temperature >= TEMP_MIN && temperature <= TEMP_MAX) ? "✅ YES" : "❌ NO");
  Serial.print("Humidity OK: "); Serial.println((humidity >= HUMID_MIN && humidity <= HUMID_MAX) ? "✅ YES" : "❌ NO");
  Serial.print("Gas Level OK: "); Serial.println((gasLevel < GAS_THRESHOLD) ? "✅ YES" : "❌ NO");
  Serial.println("==============================");
  Serial.println();
}

String getCurrentStatus() {
  bool tempOK = (temperature >= TEMP_MIN && temperature <= TEMP_MAX);
  bool humidOK = (humidity >= HUMID_MIN && humidity <= HUMID_MAX);
  bool gasOK = (gasLevel < GAS_THRESHOLD);
  
  if (!gasOK || (!tempOK && !humidOK)) {
    return "🔴 UNSAFE";
  } else if (!tempOK || !humidOK) {
    return "🟡 WARNING";
  } else {
    return "🟢 SAFE";
  }
}

void evaluateFoodSafety() {
  bool tempOK = (temperature >= TEMP_MIN && temperature <= TEMP_MAX);
  bool humidOK = (humidity >= HUMID_MIN && humidity <= HUMID_MAX);
  bool gasOK = (gasLevel < GAS_THRESHOLD);
  
  turnOffAllLEDs();
  
  if (!gasOK || (!tempOK && !humidOK)) {
    // Critical danger - Red LED
    digitalWrite(RED_LED, HIGH);
    foodStatus = "UNSAFE - Do not consume!";
    
  } else if (!tempOK || !humidOK) {
    // Warning conditions - Yellow LED
    digitalWrite(YELLOW_LED, HIGH);
    foodStatus = "WARNING - Check conditions";
    
  } else {
    // All good - Green LED
    digitalWrite(GREEN_LED, HIGH);
    foodStatus = "SAFE - Food is fresh";
  }
}

void turnOffAllLEDs() {
  digitalWrite(RED_LED, LOW);
  digitalWrite(YELLOW_LED, LOW);
  digitalWrite(GREEN_LED, LOW);
}