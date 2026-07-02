# CarTracker IoT Device
NodeMCU ESP8266 + Neo-6M GPS — sends live telemetry to the CarTracker backend.

---

## Hardware Required

| Component | Qty |
|---|---|
| NodeMCU ESP8266 (ESP-12E) | 1 |
| Neo-6M GPS Module (with antenna) | 1 |
| Jumper wires | 4 |
| USB cable (Micro-USB) | 1 |

---

## Wiring

```
Neo-6M          NodeMCU
------          -------
VCC     →       3.3V
GND     →       GND
TX      →       D2  (GPIO4)   ← GPS data flows into NodeMCU here
RX      →       D1  (GPIO5)   ← optional, only needed to configure GPS
```

> **Important:** Do NOT connect Neo-6M VCC to 5V on NodeMCU — use 3.3V only.
> Place the GPS module near a window or outdoors for a faster fix.

---

## Software Setup

### 1. Install Arduino IDE
Download from https://www.arduino.cc/en/software

### 2. Add ESP8266 Board
- Open Arduino IDE → File → Preferences
- Paste this URL in **Additional Boards Manager URLs**:
  ```
  http://arduino.esp8266.com/stable/package_esp8266com_index.json
  ```
- Tools → Board → Boards Manager → search `esp8266` → Install

### 3. Select Board
- Tools → Board → ESP8266 Boards → **NodeMCU 1.0 (ESP-12E Module)**
- Tools → Port → select your USB COM port

### 4. Install Libraries
Open Tools → Manage Libraries and install:

| Library | Author |
|---|---|
| TinyGPSPlus | Mikal Hart |
| ArduinoJson | Benoit Blanchon (install v6.x) |

ESP8266WiFi and ESP8266HTTPClient are included automatically with the board package.

---

## Configuration

Open `arduino.ino` and edit these two lines at the top:

```cpp
const char* WIFI_SSID     = "YOUR_WIFI_SSID";      // your WiFi name
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";   // your WiFi password
```

Everything else (server URL, device key, pins) is already set for the Hilux-01 device.

---

## Upload & Run

1. Connect NodeMCU to your computer via USB
2. Open `arduino.ino` in Arduino IDE
3. Click **Upload** (→ arrow button)
4. Open **Tools → Serial Monitor**, set baud rate to **115200**
5. You will see:

```
[CarTracker] Booting...
[GPS] Serial started at 9600 baud
[WiFi] Connecting to MyWiFi......
[WiFi] Connected! IP: 192.168.1.45
[GPS] Waiting for fix — satellites: 0
[GPS] Waiting for fix — satellites: 3
[HTTP] POST → {"latitude":4.1574,"longitude":9.2513,"speed":45.2,...}
[HTTP] 201 — {"status":"success","message":"Telemetry recorded",...}
```

---

## How It Works

1. On boot, connects to WiFi
2. Reads NMEA sentences from Neo-6M via SoftwareSerial (D2 pin)
3. TinyGPSPlus parses `$GPRMC` and `$GPGGA` sentences automatically
4. Every **10 seconds**, if a valid GPS fix exists, sends HTTP POST to:
   ```
   POST http://161.35.65.49:5000/api/v1/telemetry
   X-Device-Key: dev-bu-gps-001
   ```
5. Payload includes: lat, lng, speed (km/h), course, altitude, odometer (accumulated), UTC timestamp, satellites count, HDOP

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Waiting for fix" for more than 5 min | Move GPS antenna outdoors or near a window |
| WiFi connect fails | Check SSID/password, ensure 2.4 GHz network (not 5 GHz) |
| HTTP Error / no response | Check server is running: `systemctl status cartracker` |
| Wrong COM port | Device Manager (Windows) or `ls /dev/ttyUSB*` (Linux) |
| Upload fails | Hold FLASH button on NodeMCU during upload start |

---

## Send Interval

Default is **10 seconds**. To change, edit this line in `arduino.ino`:

```cpp
const unsigned long SEND_INTERVAL_MS = 10000;  // milliseconds
```

---

## Device Key

The key `dev-bu-gps-001` is seeded in the database and tied to **Hilux-01 (SW 1234 A)**.
To add a new vehicle/device, run `seed.py` or insert a Device row with a new `api_key`,
then update `DEVICE_KEY` in the sketch.
