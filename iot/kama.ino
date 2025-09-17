#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "DHT.h"

// Pin definitions
const int DHT_PIN = 4;
const int MQ135_PIN = 34; // ADC pin
const int RED_LED = 25;
const int YELLOW_LED = 26;
const int GREEN_LED = 27;

// WiFi config
const char* WIFI_SSID = "TP-Link_0B5E";
const char* WIFI_PASS = "pondokAA2022";
const char* PREDICT_URL = "kama-smartbox-production.up.railway.app/predict"; // untuk prediksi AI
const char* INGEST_URL = "kama-smartbox-production.up.railway.app/ingest";  // untuk kirim data ke database

// DHT setup
#define DHT_TYPE DHT22
DHT dht(DHT_PIN, DHT_TYPE);

// Safety thresholds (adjust after testing)
const float TEMP_MIN = 2.0;
const float TEMP_MAX = 8.0;
const float HUMID_MIN = 40.0;
const float HUMID_MAX = 70.0;
const int GAS_THRESHOLD = 2000; 

// MQ135 sampling/calibration
#define MQ135_SAMPLES 8
#define MQ135_SAMPLE_INTERVAL_MS 30
const bool CALIBRATE_MQ135 = false; 
const float MQ135_RL = 10000.0; 
const float MQ135_CLEAN_AIR_FACTOR = 3.6;

// Timing
unsigned long lastReading = 0;
unsigned long lastDetailedLog = 0;
const unsigned long READING_INTERVAL = 2000;
const unsigned long LOG_INTERVAL = 10000;

// Sensor state
float temperature = NAN;
float humidity = NAN;
int gasADC = 0;
float mqVoltage = 0.0;
float mqRS = 0.0;
float mqR0 = 0.0;
String foodStatus = "(init)";

// Forward
void turnOffAllLEDs();
void printHeader();
void printDetailedLog();
void setLEDByLabel(const String& label);
int readMQ135ADC();
float adcToVoltage(int adc);
float voltageToResistance(float vout);
float calibrateR0();

// Implementation
int readMQ135ADC() {
  long sum = 0;
  for (int i = 0; i < MQ135_SAMPLES; ++i) {
    int v = analogRead(MQ135_PIN);
    sum += v;
    delay(MQ135_SAMPLE_INTERVAL_MS);
  }
  return (int)(sum / MQ135_SAMPLES);
}

float adcToVoltage(int adc) { return (adc / 4095.0) * 3.3; }

float voltageToResistance(float vout) {
  if (vout <= 0.0) return INFINITY;
  return ((3.3 - vout) * MQ135_RL) / vout;
}

float calibrateR0() {
  Serial.println("Calibrating MQ135 R0 (clean air assumed)...");
  long sumRS = 0; int samples = 10;
  for (int i = 0; i < samples; ++i) {
    int a = readMQ135ADC(); float v = adcToVoltage(a); float rs = voltageToResistance(v);
    sumRS += (long)rs;
    Serial.print(" sample "); Serial.print(i+1); Serial.print(" adc="); Serial.print(a);
    Serial.print(" v="); Serial.print(v,3); Serial.print(" RS="); Serial.println(rs,1);
    delay(200);
  }
  float avgRS = sumRS / (float)samples; float r0 = avgRS / MQ135_CLEAN_AIR_FACTOR;
  Serial.print("Calibrated R0 = "); Serial.println(r0,1); return r0;
}

void setup() {
  Serial.begin(115200);
  delay(10000);
  dht.begin();

#ifdef ARDUINO_ARCH_ESP32
  analogSetPinAttenuation(MQ135_PIN, ADC_11db);
#endif

  pinMode(RED_LED, OUTPUT); pinMode(YELLOW_LED, OUTPUT); pinMode(GREEN_LED, OUTPUT);
  turnOffAllLEDs();

  Serial.println("=== KAMA ESP32 Food Monitor (Server AI) ===");
  printHeader();

  if (CALIBRATE_MQ135) mqR0 = calibrateR0();

  // Connect WiFi
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 30) {
    delay(500); Serial.print("."); tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\nWiFi failed!");
  }
}

void loop() {
  if (millis() - lastReading >= READING_INTERVAL) {
    temperature = dht.readTemperature();
    humidity = dht.readHumidity();
    int adc = readMQ135ADC();
    gasADC = adc;
    mqVoltage = adcToVoltage(adc);
    mqRS = voltageToResistance(mqVoltage);

    String pred_label = "unknown";

    if (WiFi.status() == WL_CONNECTED) {
      // Kirim data ke /predict (AI)
      HTTPClient http;
      http.begin(PREDICT_URL);
      http.addHeader("Content-Type", "application/json");
      StaticJsonDocument<256> doc;
      doc["temperature"] = temperature;
      doc["humidity"] = humidity;
      doc["gas_level"] = gasADC;
      doc["jenis_makanan"] = "fruits";
      String payload;
      serializeJson(doc, payload);
      int httpCode = http.POST(payload);
      if (httpCode == 200) {
        String resp = http.getString();
        StaticJsonDocument<128> respDoc;
        DeserializationError err = deserializeJson(respDoc, resp);
        if (!err && respDoc["label"]) {
          pred_label = String(respDoc["label"].as<const char*>());
          Serial.print("Predicted label from server: "); Serial.println(pred_label);
        } else {
          Serial.println("Server response parse error");
        }
      } else {
        Serial.print("HTTP error: "); Serial.println(httpCode);
      }
      http.end();

      // Kirim data ke /ingest (database)
      HTTPClient http2;
      http2.begin(INGEST_URL);
      http2.addHeader("Content-Type", "application/json");
      StaticJsonDocument<256> doc2;
      doc2["battery"] = 100; //default
      doc2["temperature"] = temperature;
      doc2["humidity"] = humidity;
      doc2["gas_level"] = gasADC;
      doc2["status"] = pred_label;
      String payload2;
      serializeJson(doc2, payload2);
      int httpCode2 = http2.POST(payload2);
      if (httpCode2 == 201) {
        Serial.println("Data berhasil dikirim ke database (kama_realtime)");
      } else {
        Serial.print("HTTP error (ingest): "); Serial.println(httpCode2);
      }
      http2.end();
    } else {
      Serial.println("WiFi not connected, skipping prediction");
    }

    Serial.print("Label diterima: [");
    Serial.print(pred_label);
    Serial.println("]");

    setLEDByLabel(pred_label);
    foodStatus = pred_label;
    printDetailedLog();
    lastReading = millis();
  }

  if (millis() - lastDetailedLog >= LOG_INTERVAL) {
    printDetailedLog(); lastDetailedLog = millis();
  }
}

void printHeader() {
  Serial.println("Time(s) | Temp(°C) | Humid(%) | Gas ADC | Status");
  Serial.println("--------|----------|----------|---------|--------");
}

void printDetailedLog() {
  Serial.println(); Serial.println("=== SENSOR REPORT ===");
  Serial.print("Temp: "); Serial.print(temperature,2); Serial.print(" °C  ");
  Serial.print("Hum: "); Serial.print(humidity,2); Serial.print(" %  ");
  Serial.print("GasADC: "); Serial.print(gasADC); Serial.print(" v:"); Serial.print(mqVoltage,3); Serial.println();
  Serial.print("RS: "); Serial.print(mqRS,2); if (mqR0>0) { Serial.print(" R0:"); Serial.print(mqR0,2); } Serial.println();
  Serial.print("Status: "); Serial.println(foodStatus);
  Serial.println("---------------------------\n");
}

String getCurrentStatus() {
  bool tOK = (temperature >= TEMP_MIN && temperature <= TEMP_MAX);
  bool hOK = (humidity >= HUMID_MIN && humidity <= HUMID_MAX);
  bool gOK = (gasADC < GAS_THRESHOLD);
  if (!gOK || (!tOK && !hOK)) return "UNSAFE";
  if (!tOK || !hOK) return "WARNING";
  return "GOOD";
}

void setLEDByLabel(const String& label) {
  turnOffAllLEDs();
  if (label == "good") {
    digitalWrite(GREEN_LED, HIGH);
  } else if (label == "warning") {
    digitalWrite(YELLOW_LED, HIGH);
  } else if (label == "bad") {
    digitalWrite(RED_LED, HIGH);
  } else {
    digitalWrite(RED_LED, HIGH); digitalWrite(YELLOW_LED, HIGH); digitalWrite(GREEN_LED, HIGH);
  }
}

void turnOffAllLEDs() { digitalWrite(RED_LED, LOW); digitalWrite(YELLOW_LED, LOW); digitalWrite(GREEN_LED, LOW); }
