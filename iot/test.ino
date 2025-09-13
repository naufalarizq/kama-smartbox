// ESP32 example: poll Flask /latest_status and drive an external RGB LED
// - Connects to WiFi
// - Every 5s, GET http://<server-ip>:<port>/latest_status
// - Map status to color: good=GREEN, warning=YELLOW, bad=RED, unknown=OFF

#include <WiFi.h>
#include <HTTPClient.h>

// ====== CONFIGURE THESE ======
const char* WIFI_SSID     = "kama123";
const char* WIFI_PASSWORD = "098767890";

// URL of your Flask server (must be reachable from ESP32)
// Example: "http://192.168.1.10:5000/latest_status"
String LATEST_STATUS_URL = "https://ddb407d35f04.ngrok-free.app/latest_status";

// Choose your LED hardware style:
// - If you use a traffic-light style module (Red/Yellow/Green separate), set USE_RYG_MODULE = true
// - If you use a single RGB LED, set USE_RYG_MODULE = false and wire RED/GREEN/BLUE
const bool USE_RYG_MODULE = true; // set true per request: warning uses dedicated Yellow only

// RYG module pins (set if USE_RYG_MODULE = true)
const int RED_PIN_RYG    = 25; // Red
const int YELLOW_PIN_RYG = 14; // Yellow (dedicated)
const int GREEN_PIN_RYG  = 26; // Green

// RGB LED pin mapping (set if USE_RYG_MODULE = false)
// Adjust to your wiring: e.g., R=25, G=26, B=27 are safe choices on many ESP32 boards
const int RED_PIN   = 25; // Red channel
const int GREEN_PIN = 26; // Green channel
const int BLUE_PIN  = 27; // Blue channel

// Set to true if your LED is Common Anode; false for Common Cathode
const bool COMMON_ANODE = false;

void setChannel(int pin, bool on) {
  // For Common Anode: LOW = ON, HIGH = OFF
  // For Common Cathode: HIGH = ON, LOW = OFF
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
  // Looks for: "key":"value" or "key":value
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

  // Otherwise read until comma or closing brace
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
  // Turn OFF initially
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
          // RED only
          setColor(true, false, false);
        }
      } else if (status == "warning") {
        if (USE_RYG_MODULE) {
          // YELLOW only (dedicated pin)
          setChannel(RED_PIN_RYG, false);
          setChannel(YELLOW_PIN_RYG, true);
          setChannel(GREEN_PIN_RYG, false);
        } else {
          // YELLOW via RGB mix (RED + GREEN)
          setColor(true, true, false);
        }
      } else if (status == "good") {
        if (USE_RYG_MODULE) {
          setChannel(RED_PIN_RYG, false);
          setChannel(YELLOW_PIN_RYG, false);
          setChannel(GREEN_PIN_RYG, true);
        } else {
          // GREEN only
          setColor(false, true, false);
        }
      } else {
        // Unknown -> OFF
        setAllOff();
      }
    } else {
      Serial.print("Request failed: ");
      Serial.println(http.errorToString(httpCode));
    }

    http.end();
  } else {
    // Try reconnecting if needed
    connectWiFi();
  }

  delay(5000); // Poll every 5 seconds
}
