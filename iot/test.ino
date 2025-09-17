
#include <WiFi.h>
#include <HTTPClient.h>

// ====== CONFIGURE THESE ======
const char* WIFI_SSID     = "kama123";
const char* WIFI_PASSWORD = "098767890";

String LATEST_STATUS_URL = "kama-smartbox-production.up.railway.app/latest_status";

const bool USE_RYG_MODULE = true;

// RYG module pins (set if USE_RYG_MODULE = true)
const int RED_PIN_RYG    = 25; 
const int YELLOW_PIN_RYG = 14; 
const int GREEN_PIN_RYG  = 26; 

const int RED_PIN   = 25; 
const int GREEN_PIN = 26; 
const int BLUE_PIN  = 27; 

const bool COMMON_ANODE = false;

void setChannel(int pin, bool on) {
  if (COMMON_ANODE) {
    digitalWrite(pin, on ? LOW : HIGH);
  } else {
    digitalWrite(pin, on ? HIGH : LOW);
  }
}

void setColor(bool r, bool g, bool b) {
  setChannel(RED_PIN, r);
  setChannel(GREEN_PIN, g);
  setChannel(BLUE_PIN, b);
}

void setAllOff() {
  if (USE_RYG_MODULE) {
    setChannel(RED_PIN_RYG, false);
    setChannel(YELLOW_PIN_RYG, false);
    setChannel(GREEN_PIN_RYG, false);
  } else {
    setColor(false, false, false);
  }
}

// Simple JSON parser helpers (very naive):
String extractJsonValue(const String& json, const String& key) {
  String pattern = String("\"") + key + "\"";
  int idx = json.indexOf(pattern);
  if (idx < 0) return "";
  int colon = json.indexOf(":", idx);
  if (colon < 0) return "";
  // Skip spaces
  int start = colon + 1;
  while (start < (int)json.length() && isspace(json[start])) start++;

  // If value is quoted string
  if (start < (int)json.length() && json[start] == '"') {
    start++;
    int end = json.indexOf('"', start);
    if (end > start) return json.substring(start, end);
    return "";
  }

  int end = start;
  while (end < (int)json.length() && json[end] != ',' && json[end] != '}' && json[end] != '\n') end++;
  String raw = json.substring(start, end);
  raw.trim();
  return raw;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 60) {
    delay(500);
    Serial.print(".");
    retry++;
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Failed to connect to WiFi.");
  }
}

void setup() {
  Serial.begin(115200);
  if (USE_RYG_MODULE) {
    pinMode(RED_PIN_RYG, OUTPUT);
    pinMode(YELLOW_PIN_RYG, OUTPUT);
    pinMode(GREEN_PIN_RYG, OUTPUT);
  } else {
    pinMode(RED_PIN, OUTPUT);
    pinMode(GREEN_PIN, OUTPUT);
    pinMode(BLUE_PIN, OUTPUT);
  }
  setAllOff();

  connectWiFi();
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(LATEST_STATUS_URL);
    int httpCode = http.GET();

    if (httpCode > 0) {
      String payload = http.getString();
      Serial.print("HTTP "); Serial.println(httpCode);
      Serial.println(payload);

      String status = extractJsonValue(payload, "status");
      status.toLowerCase();

      if (status == "bad") {
        if (USE_RYG_MODULE) {
          setChannel(RED_PIN_RYG, true);
          setChannel(YELLOW_PIN_RYG, false);
          setChannel(GREEN_PIN_RYG, false);
        } else {
          setColor(true, false, false);
        }
      } else if (status == "warning") {
        if (USE_RYG_MODULE) {
          setChannel(RED_PIN_RYG, false);
          setChannel(YELLOW_PIN_RYG, true);
          setChannel(GREEN_PIN_RYG, false);
        } else {
          setColor(true, true, false);
        }
      } else if (status == "good") {
        if (USE_RYG_MODULE) {
          setChannel(RED_PIN_RYG, false);
          setChannel(YELLOW_PIN_RYG, false);
          setChannel(GREEN_PIN_RYG, true);
        } else {
          setColor(false, true, false);
        }
      } else {
        setAllOff();
      }
    } else {
      Serial.print("Request failed: ");
      Serial.println(http.errorToString(httpCode));
    }

    http.end();
  } else {
    connectWiFi();
  }

  delay(5000);
}
