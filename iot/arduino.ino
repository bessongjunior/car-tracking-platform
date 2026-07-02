/*
 * CarTracker GPS Device — NodeMCU ESP8266 + Neo-6M
 * Sends GPS telemetry to CarTracker backend every 10 seconds.
 *
 * Libraries required (install via Arduino Library Manager):
 *   - TinyGPSPlus  by Mikal Hart
 *   - ArduinoJson  by Benoit Blanchon  (v6.x)
 *   - ESP8266WiFi  (included with ESP8266 board package)
 *   - ESP8266HTTPClient (included with ESP8266 board package)
 *
 * Board: NodeMCU 1.0 (ESP-12E Module)
 * Board Manager URL: http://arduino.esp8266.com/stable/package_esp8266com_index.json
 */

#include <TinyGPSPlus.h>
#include <SoftwareSerial.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>

// ── WiFi ─────────────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ── Server ───────────────────────────────────────────────────────────────────
const char* SERVER_URL = "http://161.35.65.49:5000/api/v1/telemetry";
const char* DEVICE_KEY = "dev-bu-gps-001";

// ── GPS Pins (SoftwareSerial) ─────────────────────────────────────────────────
// Neo-6M TX  →  NodeMCU D2 (GPIO4)   [RX for software serial]
// Neo-6M RX  →  NodeMCU D1 (GPIO5)   [TX for software serial] (optional)
static const int GPS_RX_PIN = 4;   // D2
static const int GPS_TX_PIN = 5;   // D1
static const uint32_t GPS_BAUD = 9600;

// ── Send interval ─────────────────────────────────────────────────────────────
const unsigned long SEND_INTERVAL_MS = 10000;  // 10 seconds

// ── Globals ───────────────────────────────────────────────────────────────────
TinyGPSPlus    gps;
SoftwareSerial gpsSerial(GPS_RX_PIN, GPS_TX_PIN);

unsigned long lastSendTime    = 0;
double        prevLat         = 0.0;
double        prevLng         = 0.0;
float         odometerKm      = 0.0;
bool          hasPrevPosition = false;


// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("\n\n[CarTracker] Booting...");

  gpsSerial.begin(GPS_BAUD);
  Serial.println("[GPS] Serial started at 9600 baud");

  connectWiFi();
}

// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  // Feed every available GPS byte into TinyGPSPlus
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  unsigned long now = millis();
  if (now - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = now;

    if (gps.location.isValid() && gps.location.age() < 2000) {
      accumulateOdometer();
      sendTelemetry();
    } else {
      Serial.println("[GPS] Waiting for fix — satellites: " + String(gps.satellites.value()));
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Failed — will retry on next send");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
void accumulateOdometer() {
  double lat = gps.location.lat();
  double lng = gps.location.lng();

  if (hasPrevPosition) {
    // TinyGPSPlus returns distance in metres
    double distM = TinyGPSPlus::distanceBetween(prevLat, prevLng, lat, lng);
    odometerKm += (float)(distM / 1000.0);
  }

  prevLat          = lat;
  prevLng          = lng;
  hasPrevPosition  = true;
}

// ─────────────────────────────────────────────────────────────────────────────
void sendTelemetry() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Not connected — reconnecting...");
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) return;
  }

  // Build JSON payload
  StaticJsonDocument<300> doc;
  doc["latitude"]      = gps.location.lat();
  doc["longitude"]     = gps.location.lng();
  doc["speed"]         = gps.speed.kmph();          // TinyGPSPlus converts knots → km/h
  doc["course"]        = (int)gps.course.deg();
  doc["altitude"]      = gps.altitude.meters();
  doc["engine_status"] = true;
  doc["odometer"]      = odometerKm;

  // ISO 8601 UTC timestamp from GPS
  if (gps.date.isValid() && gps.time.isValid()) {
    char ts[25];
    snprintf(ts, sizeof(ts), "%04d-%02d-%02dT%02d:%02d:%02dZ",
      gps.date.year(), gps.date.month(),  gps.date.day(),
      gps.time.hour(), gps.time.minute(), gps.time.second()
    );
    doc["timestamp"] = ts;
  }

  // Sensors — extend with any real sensor readings you add later
  JsonObject sensors = doc.createNestedObject("sensors");
  sensors["satellites"] = gps.satellites.value();
  sensors["hdop"]       = gps.hdop.value();         // GPS accuracy indicator

  String body;
  serializeJson(doc, body);

  Serial.println("[HTTP] POST → " + body);

  WiFiClient   client;
  HTTPClient   http;
  http.begin(client, SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key",  DEVICE_KEY);
  http.setTimeout(8000);

  int code = http.POST(body);

  if (code > 0) {
    Serial.printf("[HTTP] %d — %s\n", code, http.getString().c_str());
  } else {
    Serial.printf("[HTTP] Error: %s\n", http.errorToString(code).c_str());
  }

  http.end();
}
