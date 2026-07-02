# CHAPTER THREE: SYSTEM DESIGN AND ARCHITECTURE

## 3.1 Software Requirements Specification

The Software Requirements Specification (SRS) captures the complete set of functional and non-functional requirements for the Car Tracker App. It serves as the contractual baseline between stakeholders and the development team, ensuring that every feature, constraint, and quality attribute is explicitly documented before implementation commences. The SRS is organised according to the IEEE 830-1998 recommended practice for software requirements specifications [15].

### 3.1.1 Functional Requirements

Functional requirements define the specific behaviours, services, and functions that the system must provide. They are grouped by actor and module.

#### 3.1.1.1 User Management Module

**FR-UM-01 Registration:** The system shall allow new users to register by providing a valid email address, password, full name, and phone number. The password must be at least eight characters long and contain at least one uppercase letter, one lowercase letter, one digit, and one special character.

**FR-UM-02 Authentication:** The system shall authenticate registered users through a two-step flow. Step one: the user submits email and password; the system verifies credentials against bcrypt-hashed values and, if valid, generates a 6-digit one-time password (OTP) with a 5-minute expiry and dispatches it to the user's registered email address via SMTP. Step two: the user submits the OTP; the system validates it against an in-memory store and, on success, issues a signed JWT access token (1-hour expiry, HS256) whose payload encodes the user's `role`, `org_id`, and `is_super_admin` claims.

**FR-UM-03 Role Assignment:** The system shall support role-based access within each organisation through an organisation membership model. Two roles exist: `admin` (full CRUD privileges over vehicles, devices, geofences, and alerts within the organisation) and `user` (read-only access to fleet data and alert history). A single user may hold different roles in different organisations.

**FR-UM-04 Password Reset:** The system shall allow users to request a password reset via a time-limited (30-minute) token sent to their registered email address.

**FR-UM-05 Profile Management:** The system shall allow authenticated users to update their profile information, change passwords, and view active login sessions.

#### 3.1.1.2 Device Management Module

**FR-DM-01 Device Registration:** An authenticated `owner` shall be able to register a new tracking device by providing a unique device identifier (UUID), vehicle name, vehicle registration number, and optional description. The system shall persist the device record and associate it with the owner's account.

**FR-DM-02 Device Configuration:** The system shall allow the `owner` to configure telemetry parameters including update interval (5–60 seconds), speed threshold (km/h), and active GNSS constellations (GPS, GLONASS, QZSS). Configuration changes shall be pushed to the device via a configuration endpoint on the next heartbeat.

**FR-DM-03 Device Status Monitoring:** The system shall display real-time device status including last seen timestamp, battery voltage, Wi-Fi signal strength (RSSI), and number of satellites in view.

**FR-DM-04 Device Deactivation:** The `owner` shall be able to deactivate or permanently delete a device. Deactivation shall stop telemetry ingestion but retain historical data for 90 days. Deletion shall cascade to remove all associated waypoints, geofences, and alerts.

#### 3.1.1.3 Telemetry and Tracking Module

**FR-TT-01 Location Ingestion:** The system shall expose a REST endpoint `/api/v1/telemetry` that accepts POST requests containing JSON payloads with fields: `device_id`, `latitude`, `longitude`, `altitude`, `speed`, `course`, `satellites`, `fix_quality`, `timestamp`, and `battery_voltage`. The endpoint shall validate coordinate bounds (−90° to +90° latitude, −180° to +180° longitude) and reject malformed payloads with HTTP 400.

**FR-TT-02 Real-Time Tracking:** Upon each telemetry ingestion, the system shall push the vehicle's current GPS state (`lat`, `lng`, `heading`, `speed`, `updatedAt`) to Firebase Realtime Database at the path `/vehicles/{vehicle_id}/gps`. The Flutter application shall subscribe to this path via the Firebase SDK to receive location updates within one second of ingestion without polling.

**FR-TT-03 Historical Route Storage:** The system shall persist every telemetry point to the PostgreSQL `telemetry` table, indexed by `(vehicle_id, timestamp)`. Each row shall capture latitude, longitude, altitude, speed, course, engine status, odometer, and an extensible `sensors` JSONB field for future hardware sensor data.

**FR-TT-04 Offline Buffer Sync:** The device firmware shall buffer up to 1,000 telemetry records in SPIFFS flash memory when network connectivity is unavailable. Upon reconnection, the firmware shall transmit buffered records in chronological order via a bulk upload endpoint `/api/v1/telemetry/bulk`.

#### 3.1.1.4 Geofencing Module

**FR-GF-01 Geofence Creation:** The system shall allow an `admin` to create circular geofences (centre lat/lon + radius in metres) and polygonal geofences (ordered GeoJSON coordinate ring). Geometry shall be stored as JSONB in the `geofences` table, using `{center: {lat, lng}, radius_m}` for circles and a GeoJSON Polygon object for polygons. Geofences shall be scoped to an organisation and shall carry per-zone speed limit and entry/exit notification flags.

**FR-GF-02 Boundary Evaluation:** Upon ingestion of each telemetry point, the system shall evaluate whether the GPS coordinate lies within every active geofence belonging to the organisation. Circular geofences shall be evaluated using the Haversine great-circle distance formula; polygonal geofences shall be evaluated using a ray-casting algorithm operating on the GeoJSON coordinate ring. Both algorithms shall execute in the Python application layer.

**FR-GF-03 Alert Generation:** When a telemetry point is inside a geofence whose `notify_on_enter` flag is set, or outside a geofence whose `notify_on_exit` flag is set, the system shall create an `Alert` record of type `geofence` and severity `medium`, with a descriptive message identifying the vehicle, zone name, and event direction. The system shall immediately dispatch an FCM push notification to all FCM tokens registered for that organisation.

**FR-GF-04 Geofence Scheduling:** The system shall support time-based geofence activation schedules (e.g., active only between 18:00 and 06:00). Alerts shall be suppressed outside scheduled windows.

#### 3.1.1.5 Speed Monitoring Module

**FR-SM-01 Threshold Configuration:** The `admin` shall configure a speed limit (km/h) per geofence zone. The system shall store the `speed_limit` on the `geofences` table, allowing different speed thresholds for different zones within the same organisation.

**FR-SM-02 Overspeed Detection:** For each telemetry point, the system shall compare `speed` against the threshold. If `speed > threshold` and the previous point was below threshold, the system shall generate an `OVERSPEED` alert and dispatch a push notification.

**FR-SM-03 Hysteresis:** To prevent alert flicker, the system shall require speed to drop below 95% of the threshold before clearing the overspeed state.

#### 3.1.1.6 Alerting and Notification Module

**FR-AN-01 In-App Alert Inbox:** The Flutter application shall display an alert inbox sorted by timestamp descending. Users shall view alerts of type `geofence`, `speed`, `sos`, and `offline`, each with severity (`low`, `medium`, `high`, `critical`), a human-readable message, and a resolved/unresolved status. An `admin` shall be able to mark alerts as resolved via `PATCH /api/v1/alerts/{id}/resolve`.

**FR-AN-02 Push Notifications:** The system shall integrate Firebase Cloud Messaging (FCM) to deliver push notifications to Android and iOS devices. Notifications shall include title, body, alert type, and deep-link to the relevant map view or alert detail screen.

**FR-AN-03 Alert History:** The system shall retain alert records for 90 days. Users shall be able to export alert history as CSV or JSON via the mobile application.

#### 3.1.1.7 History and Analytics Module

**FR-HA-01 Route Replay:** The system shall allow users to select a date range and retrieve all waypoints for a device within that range. The Flutter application shall render the waypoints as an animated polyline on the map, with a scrubber control to replay movement over time.

**FR-HA-02 Distance Summary:** The system shall compute total distance travelled within a selected date range by summing Haversine distances between consecutive telemetry records for the vehicle, returning the result in kilometres.

**FR-HA-03 Stop Detection:** The system shall identify stop points where speed remained below 2 km/h for at least 5 minutes. Stop points shall be displayed as markers with duration and timestamp.

**FR-HA-04 GPX Export:** The system shall allow users to export route data as a GPX (GPS Exchange Format) file compatible with third-party mapping tools.

#### 3.1.1.8 Multi-Tenant SaaS Platform Module

The backend is architected as a multi-tenant Software-as-a-Service (SaaS) platform. Multiple independent organisations (tenants) share a single deployed application instance and database cluster, with all data access boundaries enforced in the application layer through organisation-scoped queries and JWT claims.

**FR-MT-01 Organisation Provisioning:** The system shall support the creation of multiple independent organisations, each identified by a unique UUID and human-readable slug. An organisation represents a fleet operator — a logistics company, a vehicle hire firm, or a private fleet owner — that manages its own vehicles, devices, geofences, and alerts entirely independently of other organisations on the same platform.

**FR-MT-02 Tenant Data Isolation:** Every data entity — vehicles, devices, telemetry records, geofences, alerts, FCM tokens, and audit logs — shall carry an `organization_id` foreign key. The application layer shall append `filter_by(organization_id=org_id)` to every database query, where `org_id` is sourced from the authenticated user's JWT claims and never from client-supplied request parameters, preventing horizontal privilege escalation between tenants.

**FR-MT-03 Organisation Membership:** Users shall be associated with organisations through an `organization_members` join table that records one role per `(user_id, organization_id)` pair. A single user account may belong to multiple organisations simultaneously, each with an independently assigned role. The system shall resolve the active organisation context from the `org_id` JWT claim present in every authenticated request.

**FR-MT-04 Intra-Organisation Role-Based Access Control:** The system shall enforce role-based access within each organisation. The `admin` role shall be required to create or delete geofences (`POST /geofences`, `DELETE /geofences/{id}`), and shall be the only role capable of resolving alerts. The `user` role shall have read-only access to vehicles, telemetry history, geofence lists, and alert inbox. Role checks shall be implemented via a `@require_role()` decorator applied at the route level, returning HTTP 403 for insufficient privilege.

**FR-MT-05 Hardware Device Authentication:** Physical GPS tracking devices shall authenticate to the telemetry ingestion endpoint using a static `X-Device-Key` header rather than a user JWT. Each `Device` record in the database carries a unique `api_key` (64-character UUID hex). The backend shall resolve the device and its assigned vehicle from this key, then attribute the telemetry to the correct organisation without requiring any user session context. This decoupling allows hardware devices to ingest data continuously without managing token lifetimes.

**FR-MT-06 Organisation-Scoped Push Notifications:** When an alert is created for a vehicle, the system shall dispatch FCM push notifications to every mobile device registered under the same `organization_id`. FCM tokens shall be stored in the `device_fcm_tokens` table keyed by `(user_id, organization_id)`, ensuring that notifications are broadcast to all members of the affected tenant and never to members of a different organisation.

**FR-MT-07 Organisation-Scoped Audit Trail:** The system shall record significant administrative and authentication events to the `audit_logs` table with fields: `organization_id`, `user_id`, `action`, `target_type`, `target_id`, `changes` (JSONB), `ip_address`, and `timestamp`. Audit logs shall be readable only within their own organisation context, supporting compliance review, forensic investigation, and accountability without cross-tenant data exposure.

**FR-MT-08 Organisation Settings Extensibility:** Each organisation record shall carry a `settings` JSONB column that stores tenant-specific configuration (e.g., notification preferences, dashboard defaults, branding metadata). This schema-free field allows per-tenant customisation to evolve without requiring database schema migrations for the shared platform.

### 3.1.2 Non-Functional Requirements

Non-functional requirements specify the quality attributes, constraints, and operational characteristics of the system.

#### 3.1.2.1 Performance Requirements

**NFR-PF-01 Response Time:** The REST API shall respond to 95% of requests within 200 ms under normal load (<100 concurrent connections). Telemetry ingestion endpoints shall process single-point payloads within 100 ms.

**NFR-PF-02 Throughput:** The backend shall sustain a minimum of 50 telemetry requests per second without degradation of response time or database connection pool exhaustion.

**NFR-PF-03 Map Rendering:** The Flutter application shall render the map view and overlay markers within 2 seconds of state emission on a mid-range Android device (e.g., Snapdragon 665, 4 GB RAM).

**NFR-PF-04 TTFF:** The hardware tracker shall achieve a cold-start TTFF of ≤35 seconds and a hot-start TTFF of ≤3 seconds under open-sky conditions.

#### 3.1.2.2 Security Requirements

**NFR-SC-01 Encryption:** All API communications shall be encrypted using TLS 1.2 or higher with valid X.509 certificates. HSTS shall be enforced with a max-age of 31,536,000 seconds (one year).

**NFR-SC-02 Authentication:** The system shall use a two-factor authentication flow: bcrypt credential verification (cost factor 12) followed by a time-limited OTP delivered to the user's registered email. JWT access tokens shall be signed with HS256 using a secret loaded from an environment variable (never hard-coded), with a configurable expiry defaulting to 1 hour. The JWT payload shall embed `role`, `org_id`, and `is_super_admin` claims to enable stateless authorisation at every downstream endpoint.

**NFR-SC-03 Authorisation:** Role-Based Access Control shall be enforced at every protected endpoint. unauthorised access attempts shall return HTTP 403 and be logged for audit.

**NFR-SC-04 Input Sanitisation:** All user inputs shall be validated against Marshmallow schemas before reaching service logic. SQL queries shall use parameterised statements exclusively through the SQLAlchemy ORM to prevent injection attacks.

**NFR-SC-05 Rate Limiting:** The API shall enforce per-IP rate limits of 100 requests per minute and per-user login attempt limits of 10 per 5 minutes. Exceeded limits shall return HTTP 429 with a `Retry-After` header.

#### 3.1.2.3 Availability and Reliability Requirements

**NFR-AR-01 Uptime:** The backend API shall target 99.5% uptime excluding scheduled maintenance windows. Health check endpoints (`/health`, `/ready`) shall be exposed for load balancer and monitoring integration.

**NFR-AR-02 Data Durability:** Telemetry data shall be persisted with Write-Ahead Logging (WAL) enabled in PostgreSQL. Daily automated backups shall be retained for 30 days.

**NFR-AR-03 Device Resilience:** The embedded firmware shall implement a watchdog timer with 8-second timeout. If the main loop hangs, the ESP8266 shall automatically reset and resume operation. Network failures shall trigger exponential backoff with jitter (1 s, 2 s, 4 s, 8 s, max 60 s).

#### 3.1.2.4 Scalability Requirements

**NFR-SL-01 Horizontal Scaling:** The backend shall be stateless to allow horizontal scaling behind a load balancer. Session state shall not be stored in server memory.

**NFR-SL-02 Database Partitioning:** The `telemetry` table shall support time-based declarative partitioning (e.g., monthly partitions on the `timestamp` column) to maintain query performance as data volume grows beyond 10 million rows across all tenants.

#### 3.1.2.5 Usability Requirements

**NFR-US-01 Onboarding:** A first-time user shall complete registration and device pairing within 5 minutes without external documentation.

**NFR-US-02 Accessibility:** The Flutter application shall support dynamic font scaling and screen reader labels (TalkBack, VoiceOver) on all interactive widgets.

**NFR-US-03 Offline Support:** The mobile application shall cache the last known location and 7 days of history for offline viewing. Actions requiring connectivity shall queue and sync automatically upon restoration.

#### 3.1.2.6 Compatibility Requirements

**NFR-CP-01 Mobile Platforms:** The Flutter application shall support Android 5.0 (API 21) through Android 14 (API 34) and iOS 13 through iOS 17.

**NFR-CP-02 Browser Support:** The web admin dashboard (if implemented) shall be compatible with Chrome 90+, Firefox 88+, Safari 14+, and Edge 90+.

**NFR-CP-03 Hardware:** The embedded firmware shall compile under Arduino IDE 2.x and PlatformIO with ESP8266 core version 3.1.0 or later.

#### 3.1.2.7 Multi-Tenant SaaS Requirements

**NFR-MT-01 Tenant Isolation:** No query, API response, push notification, or audit log entry shall expose data belonging to one organisation to a user authenticated as a member of a different organisation. Isolation shall be enforced exclusively at the application layer — every SQLAlchemy query targeting organisation-scoped tables shall include a `filter_by(organization_id=...)` clause driven by the `org_id` JWT claim, not by any client-supplied parameter.

**NFR-MT-02 Stateless Tenancy Context:** The backend shall remain stateless with respect to tenant context. All organisation identity information required to process a request shall be derived from the JWT access token issued at login. No server-side session or in-memory tenant cache shall be required for normal request processing, enabling horizontal scaling without sticky sessions.

**NFR-MT-03 Zero-Downtime Onboarding:** Provisioning a new organisation tenant shall require only a database insert into the `organizations` and `organization_members` tables. No application restart, configuration change, or code deployment shall be required to onboard an additional fleet operator to the platform.

**NFR-MT-04 Per-Tenant FCM Scoping:** Push notification dispatch shall be bounded strictly to the FCM tokens registered under the alert's `organization_id`. The `FCMService.notify_org()` method shall query tokens by `organization_id` and use Firebase Multicast delivery, ensuring that alerts are never delivered to users outside the originating organisation regardless of how many tenants share the platform.

**NFR-MT-05 Device Credential Independence:** Hardware device API keys (`X-Device-Key`) shall be generated independently of user accounts and JWT lifecycles. A device key shall remain valid continuously for the operational lifetime of the hardware unit, unaffected by user password changes, JWT expiry, or account deactivation, ensuring uninterrupted telemetry ingestion from deployed GPS trackers.

**NFR-MT-06 Shared Infrastructure Efficiency:** All tenants shall share the same PostgreSQL database instance, Flask application processes, and Firebase project. Tenant separation shall be achieved through `organization_id` scoping rather than physical infrastructure isolation, keeping operational costs proportional to data volume and request load rather than to the number of tenants.

## 3.2 System Architecture Design

The system adopts a three-tier client-server architecture comprising the Embedded Hardware Tier, the Application Backend Tier, and the Mobile Client Tier. This separation of concerns ensures that each tier can evolve independently, be replaced, or be scaled without affecting the others. The architecture is depicted conceptually as follows:

**Description of Figure 3.1 — Three-Tier System Architecture:**
The diagram shows three horizontal layers. The bottom layer, labelled "Embedded Hardware Tier," contains the Node MCU ESP8266 connected to the Neo-7M GPS module and power regulation circuitry. An arrow labelled "HTTPS POST /api/v1/telemetry (X-Device-Key)" points upward from this tier to the middle layer. The middle layer, labelled "Application Backend Tier," contains three sub-components arranged left-to-right: an Nginx reverse proxy, a Gunicorn Flask application server, and a PostgreSQL database. A Firebase Realtime Database node sits to the right of the application server, connected by an arrow labelled "GPS push on every telemetry ingestion." Arrows indicate that the proxy forwards requests to Flask, Flask queries PostgreSQL, and Flask writes real-time GPS state to Firebase RTDB and dispatches FCM push notifications via Google's Firebase services. The top layer, labelled "Mobile Client Tier," shows a smartphone icon running the Flutter application. Bidirectional REST arrows connect the smartphone to the Nginx proxy. A second arrow connects the smartphone to Firebase RTDB directly for real-time location streaming. A third arrow connects to the FCM cloud for push notification receipt. The multi-tenant nature is shown by a bracket annotating the middle layer: "Shared infrastructure — N organisations, isolated by org_id."

### 3.2.1 Embedded Hardware Tier

The Embedded Hardware Tier is responsible for sensing, parsing, buffering, and transmitting location telemetry. It operates autonomously once powered and configured, requiring no human intervention during normal operation.

**Components:**
- **Node MCU ESP8266 V3:** Serves as the microcontroller and Wi-Fi communication hub. It runs the custom firmware loop: wake → read UART → parse NMEA → build JSON → POST to API → sleep (if configured).
- **u-blox Neo-7M:** The GNSS receiver outputs NMEA 0183 sentences at 1 Hz via UART at 9600 baud. The module is configured via UBX protocol messages to enable GPS + GLONASS + QZSS reception and to set the navigation mode to "Automotive."
- **Power Subsystem:** A LM2596 DC-DC buck converter steps down 12 V vehicle battery to 5 V. An AMS1117-3.3 LDO regulator provides 3.3 V to the Neo-7M VCC and UART logic levels. A 470 µF electrolytic capacitor across the Neo-7M supply rails suppresses voltage transients from vehicle electrical noise.
- **Antenna:** An active ceramic patch antenna (28 dB gain, 3 m cable) with magnetic mount is placed on the vehicle roof for optimal sky visibility.

**Data Flow:**
1. Neo-7M acquires satellite signals and outputs `$GPGGA`, `$GPRMC`, `$GPGSV`, and `$GPGSA` sentences.
2. ESP8266 reads the UART buffer using `SoftwareSerial` (pins D5/RX, D6/TX) at 9600 baud.
3. `TinyGPS++` library parses the sentences, extracting latitude, longitude, altitude, speed, course, satellites, and HDOP.
4. The firmware constructs a JSON object: `{"device_id":"...","lat":4.15,"lon":9.28,"speed":45.2,"sat":8,"ts":"2026-05-14T08:30:00Z"}`.
5. `ESP8266HTTPClient` opens a TLS connection to the API endpoint and POSTs the payload.
6. On HTTP 201 success, the record is removed from the local SPIFFS buffer if it was a backlog item. On failure, the record is appended to the buffer.

The Neo-7M calculates ground speed internally by measuring the Doppler shift of the L1 carrier signals from multiple satellites, solving for the receiver's velocity vector. This computed speed is then embedded directly into the $GPRMC NMEA sentence as the 'Speed Over Ground' field, requiring no additional computation from the microcontroller or backend.

### 3.2.2 Application Backend Tier

The Application Backend Tier is the central nervous system of the tracker, responsible for request handling, business logic execution, data persistence, and notification dispatch.

**Components:**
- **Nginx Reverse Proxy:** Listens on port 443, terminates TLS using Let's Encrypt certificates, enforces HSTS, and forwards requests to the Gunicorn upstream on port 8000. Nginx also serves static files (admin dashboard assets if applicable) and handles compression (gzip/brotli).
- **Gunicorn Workers:** Runs the Flask WSGI application using synchronous workers. Worker count is set to `(2 × CPU cores) + 1`, enabling concurrent request handling through process-based parallelism without requiring an asynchronous runtime.
- **Flask Application:** Organised as a single blueprint (`api_bp`) registered at the `/api/v1` prefix, exposing route groups for: `auth`, `vehicles`, `telemetry`, `geofences`, `alerts`, `users`, and development-only `firebase` helpers. The application initialises SQLAlchemy, Firebase Admin SDK, and FCM at startup. Interactive API documentation is served via Flasgger (Swagger UI) at `/api/v1/docs/`.
- **PostgreSQL:** Stores relational data including users, organisations, vehicles, devices, telemetry records, geofences, alerts, and audit logs. Connection pooling is managed by SQLAlchemy with `pool_pre_ping` enabled for stale-connection detection.
- **Firebase Realtime Database:** Receives real-time GPS push updates from the backend on every successful telemetry ingestion event. The mobile client subscribes to `/vehicles/{vehicle_id}/gps` for sub-second location streaming without polling. Each update payload carries `lat`, `lng`, `heading`, `speed`, and a millisecond `updatedAt` epoch timestamp.
- **Firebase Cloud Messaging:** External service used for push notification delivery. The backend stores per-user FCM tokens in the `device_fcm_tokens` table, keyed by `(user_id, organization_id)`, and dispatches targeted notifications on geofence and overspeed events.

### 3.2.3 Mobile Client Tier

The Mobile Client Tier provides the primary human-computer interface for vehicle owners, drivers, and viewers. It is built as a single Flutter codebase targeting both Android and iOS.

**Components:**
- **Flutter Engine:** Renders UI at 60 FPS using the Skia graphics engine. The application uses `MaterialApp` with custom theming for light and dark modes.
- **Google Maps Flutter Plugin:** Renders interactive map tiles with custom vehicle marker icons, polylines for routes, and polygon overlays for geofences.
- **BLoC State Management:** Each feature module has a dedicated BLoC: `AuthBloc`, `MapBloc`, `GeofenceBloc`, `AlertBloc`, `HistoryBloc`. BLoCs consume repository classes that wrap HTTP calls.
- **Local Database:** SQLite (via `sqflite` plugin) caches waypoints, alerts, and user settings for offline access. A background sync task runs every 15 minutes when the app is foregrounded.
- **FCM Client:** Receives push notifications in foreground, background, and terminated states. Notifications are decoded and routed to the appropriate screen via deep links (`/alert/{id}`, `/map?device={id}`).

## 3.3 Detailed Module Design

This section decomposes the system into five primary modules: Hardware/Firmware, Backend API, Mobile Application, Database, and Security. Each module is described through its sub-components, interfaces, data flows, and design rationale.

### 3.3.1 Hardware/Firmware Module

**Description of Figure 3.2 — Hardware Schematic and Pin Connections:**
The diagram shows a rectangular block labelled "Node MCU ESP8266 V3" on the left, with labelled pins along its left and right edges. Pin D5 (GPIO14) is connected via a line to the Neo-7M TX pin (software serial RX). Pin D6 (GPIO12) is connected to the Neo-7M RX pin (software serial TX). The Neo-7M VCC pin is connected to the 3.3 V output of the AMS1117 regulator. The Neo-7M GND pin is tied to the common ground plane. The AMS1117 input receives 5 V from the LM2596 buck converter output. The LM2596 input is fused (3 A blade fuse) and connected to the vehicle 12 V battery positive terminal. An antenna symbol sits atop the Neo-7M block, connected via a U.FL connector. A small SPIFFS chip icon is drawn inside the ESP8266 block to represent flash buffering.

**Firmware Architecture:**
The firmware is structured as a non-preemptive event loop with the following tasks:

1. **Setup Phase:**
   - Initialise serial ports: `Serial` (USB debug, 115200 baud) and `SoftwareSerial` (Neo-7M, 9600 baud).
   - Mount SPIFFS and read `config.json` (Wi-Fi SSID, password, API endpoint, device UUID, update interval).
   - Connect to Wi-Fi using `WiFiManager` fallback captive portal if credentials are absent or connection fails.
   - Initialise NTP client (`pool.ntp.org`) to obtain UTC timestamps.
   - Configure Neo-7M via UBX-CFG-GNSS message to enable GPS + GLONASS + QZSS.

2. **Loop Phase (1 Hz execution):**
   - Read all available bytes from `SoftwareSerial` into a circular buffer.
   - Feed buffer to `TinyGPS++` parser until a complete sentence is decoded.
   - If `gps.location.isValid()` and `gps.location.age() < 5000` ms:
     - Build JSON telemetry object.
     - If Wi-Fi connected and `HTTPClient` POST succeeds → clear one buffered record if buffer non-empty.
     - Else → append JSON to SPIFFS buffer (max 1,000 records, FIFO eviction).
   - If `millis() - lastConfigCheck > 300000` (5 minutes), perform a lightweight GET to `/api/v1/devices/{id}/config` to check for remote configuration changes.
   - Pet the watchdog (`ESP.wdtFeed()`).

3. **Power Management:**
   - In normal mode, the ESP8266 draws ~80 mA at 5 V. With Wi-Fi active, current peaks to ~150 mA during transmission.
   - A `delay(1000)` at the end of the loop yields the CPU to the Wi-Fi stack, reducing average power.
   - Deep sleep is not used in continuous tracking mode because the ESP8266 cannot maintain UART reception while sleeping. However, a future enhancement could use `ESP.deepSleep()` with a 60-second wake interval for low-power parking mode.

**Interface Specification:**
- **UART Protocol:** NMEA 0183 v4.11, 9600 baud, 8N1.
- **API Protocol:** HTTPS, JSON Content-Type, TLS 1.2 minimum.
- **Buffer Format:** SPIFFS file `/buffer.jsonl`, newline-delimited JSON objects.

### 3.3.2 Backend API Module

**Description of Figure 3.3 — Backend API Module Structure:**
The diagram shows a layered architecture. At the top, a row of rectangles represents HTTP routes registered on the single `api_bp` blueprint: `POST /auth/login`, `POST /auth/verify-otp`, `GET /vehicles`, `POST /telemetry`, `POST /geofences`, `GET /alerts`, `GET /users/me`. These routes feed into a middle layer of service classes: `AuthService`, `TelemetryService`, `AlertService`, `FCMService`. Each service connects downward to the Data Access layer: SQLAlchemy ORM models — `User`, `Vehicle`, `Device`, `Telemetry`, `Geofence`, `Alert`. On the right side, external adapters are shown: `FirebaseRTDB`, `FCMClient`, `JWTManager` (flask-jwt-extended), and `GmailSMTP`. Arrows indicate dependency direction: routes depend on services, services depend on ORM models and external adapters, and ORM models depend on the synchronous SQLAlchemy `Session` backed by PostgreSQL.

**Blueprint Design:**

**Auth Blueprint (`/api/v1/auth`):**
- `POST /login` — Accepts `{email, password}`. Validates credentials against bcrypt-hashed password. On success, generates a 6-digit OTP, stores it in an in-memory dictionary with a 5-minute expiry, and dispatches it to the user's registered email via Gmail SMTP. Returns `{user_id, otp_required: true}`.
- `POST /verify-otp` — Accepts `{user_id, otp}`. Validates OTP against the in-memory store, checks expiry, then issues a JWT access token (1-hour expiry) signed with HS256. Additional JWT claims carry `role`, `org_id`, and `is_super_admin` for downstream authorisation decisions.

**Vehicle Blueprint (`/api/v1/vehicles`):**
- `GET /` — Lists all vehicles belonging to the authenticated user's organisation (scoped by `org_id` claim). Returns id, name, licence plate, VIN, vehicle type, status, and last heartbeat timestamp.
- `GET /{vehicle_id}` — Retrieves a single vehicle record with full `extra_data` JSONB payload.

**Telemetry Blueprint (`/api/v1/telemetry`):**
- `POST /` — Authenticated by `X-Device-Key` header (not JWT). Ingests a single GPS telemetry point. The `TelemetryService.ingest()` pipeline:
  1. Persists a `Telemetry` row linked to the device's assigned vehicle.
  2. Updates the vehicle's `last_heartbeat` and `status` fields.
  3. Pushes `{lat, lng, heading, speed, updatedAt}` to Firebase RTDB at `/vehicles/{vehicle_id}/gps`.
  4. Evaluates all active geofences via Haversine (circle) or ray-casting (polygon) and creates `Alert` records for entry/exit transitions.
  5. Compares speed against any active geofence speed limit and creates an overspeed `Alert` if exceeded.
  6. Dispatches FCM push notifications for every generated alert.
  Returns HTTP 201 with `{telemetry_id}`.

**Geofence Blueprint (`/api/v1/geofences`):**
- `GET /` — Lists active geofences for the organisation, including fence type, JSONB geometry, speed limit, and notification flags.
- `POST /` — Requires `admin` role. Body: `{name, fence_type (circle|polygon), geometry, speed_limit, notify_on_enter, notify_on_exit}`. Geometry is stored as JSONB (`{center: {lat, lng}, radius_m}` for circles; GeoJSON Polygon for polygons).
- `DELETE /{id}` — Soft-delete (sets `is_active = false`). Requires `admin` role.

**Alert Blueprint (`/api/v1/alerts`):**
- `GET /` — Returns up to 100 unresolved alerts for the organisation, ordered newest-first. Accepts `?resolved=true` to include already-resolved alerts.
- `PATCH /{id}/resolve` — Marks an alert as resolved, recording the resolving user ID and timestamp.

**Users Blueprint (`/api/v1/users`):**
- `GET /me` — Returns the authenticated user's profile (`full_name`, `email`, `role`, `organization`), with claims sourced from the JWT and membership data fetched from the database.

**Device FCM Blueprint (`/api/v1/devices`):**
- `POST /fcm-token` — Registers or updates the FCM push-notification token for the authenticated user, keyed by `(user_id, organization_id)`.

### 3.3.3 Mobile Application Module

**Description of Figure 3.4 — Flutter Application Module Architecture:**
The diagram shows a vertical stack. At the bottom, the "Data Layer" contains three boxes: `ApiClient` (Dio HTTP wrapper), `LocalDatabase` (SQLite), and `FCMService`. Above that, the "Repository Layer" contains: `AuthRepository`, `DeviceRepository`, `LocationRepository`, `GeofenceRepository`, `AlertRepository`. Above that, the "BLoC Layer" contains: `AuthBloc`, `MapBloc`, `GeofenceBloc`, `AlertBloc`, `HistoryBloc`. At the top, the "Presentation Layer" contains Flutter widgets: `LoginScreen`, `DashboardScreen`, `MapWidget`, `GeofenceEditor`, `AlertInbox`, `HistoryPlayer`. Arrows show that BLoCs depend on Repositories, Repositories depend on Data Layer, and Widgets depend on BLoCs via `BlocProvider` and `BlocBuilder`.

**Feature Module Descriptions:**

**Authentication Flow:**
- `LoginScreen` → dispatches `LoginSubmitted` event → `AuthBloc` calls `AuthRepository.login()` → emits `AuthAuthenticated` or `AuthFailure`.
- On success, JWT tokens are stored in `FlutterSecureStorage`. The `ApiClient` intercepts all subsequent requests to inject the `Authorization: Bearer <token>` header.
- Token expiry is handled transparently: on HTTP 401, the `ApiClient` attempts silent refresh using the stored refresh token. If refresh fails, the user is redirected to `LoginScreen`.

**Dashboard (Map) Screen:**
- `MapBloc` initialises with `MapInitial` state. On `MapStarted`, it subscribes to a periodic timer (every 5 seconds) that calls `LocationRepository.getLatest(deviceId)`.
- State transitions: `MapLoading` → `MapLocationLoaded(LatLng position, double speed, int satellites)`.
- `MapWidget` (GoogleMap) recentres the camera on the new position with a custom `BitmapDescriptor` car icon rotated by the `course` bearing.
- A `SpeedometerWidget` overlays the bottom-right corner, displaying speed in km/h with colour coding: green (<threshold), amber (threshold to 1.2×), red (>1.2×).

**Geofence Editor:**
- `GeofenceBloc` manages creation mode. The user taps the map to drop a centre pin, then drags a radius slider for circular geofences.
- For polygonal geofences, the user taps multiple points on the map; `Polygon` widget renders the editable shape. A "Complete" button dispatches `GeofenceSubmitted` with the vertex list.
- The backend validates polygon closure (first vertex == last vertex) and minimum area (≥100 m²) to prevent accidental micro-geofences.

**Alert Inbox:**
- `AlertBloc` fetches paginated alerts on scroll. Each alert card shows: icon (geofence entry/exit or speed), device name, timestamp, and location snippet.
- Tapping a card navigates to `MapScreen` with deep-link parameters centred on the alert coordinates and a temporary pulsing marker.
- Swipe-right marks as read; swipe-left deletes the alert locally (soft delete on backend).

**History Player:**
- `HistoryBloc` fetches waypoints for a selected date range. If >5,000 points, the backend returns Douglas-Peucker simplified polylines to reduce payload size.
- `HistoryPlayer` renders the full polyline in grey and a progress polyline in blue. A `Slider` controls playback speed (1×, 2×, 4×). Stop points are rendered as red circles with `InfoWindow` showing dwell time.

### 3.3.4 Database Module

**Description of Figure 3.5 — Entity-Relationship Diagram (ERD):**
The diagram shows six entity rectangles connected by relationship lines. `users` (1) is connected to `devices` (N) via "owns". `devices` (1) is connected to `waypoints` (N) via "generates". `devices` (1) is connected to `geofences` (N) via "monitors". `devices` (1) is connected to `alerts` (N) via "triggers". `users` (N) is connected to `refresh_tokens` (N) via "has". `users` (N) is connected to `user_fcm_tokens` (N) via "subscribes". Each entity box lists its primary key (underlined) and key attributes. Foreign keys are indicated with (FK) notation. The `waypoints` table includes a `geom` attribute of type `POINT`. The `geofences` table includes a `geom` attribute of type `POLYGON`. The `alerts` table includes `alert_type` with enumerated values.

**Schema Definition:**

**Table: `organizations`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK, default uuid4() |
| name | VARCHAR(100) | NOT NULL |
| slug | VARCHAR(100) | UNIQUE, NOT NULL |
| settings | JSONB | default {} |
| is_active | BOOLEAN | NOT NULL, default true |
| created_at | TIMESTAMP | NOT NULL, default now() |
| updated_at | TIMESTAMP | NOT NULL, default now() |

**Table: `users`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK, default uuid4() |
| email | VARCHAR(120) | UNIQUE, NOT NULL |
| password_hash | VARCHAR(256) | NOT NULL |
| full_name | VARCHAR(100) | |
| is_super_admin | BOOLEAN | NOT NULL, default false |
| last_login | TIMESTAMP | |
| is_active | BOOLEAN | NOT NULL, default true |
| created_at | TIMESTAMP | NOT NULL, default now() |
| updated_at | TIMESTAMP | NOT NULL, default now() |

**Table: `organization_members`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id |
| organization_id | UUID | FK → organizations.id |
| role | VARCHAR(20) | NOT NULL, default 'user' |
| created_at | TIMESTAMP | NOT NULL, default now() |

*Note:* A unique constraint on `(user_id, organization_id)` prevents duplicate memberships. Roles are `admin` (full CRUD over geofences, devices) and `user` (read-only fleet access).

**Table: `vehicles`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | FK → organizations.id |
| name | VARCHAR(50) | NOT NULL |
| license_plate | VARCHAR(20) | UNIQUE, NOT NULL |
| vin | VARCHAR(17) | UNIQUE |
| vehicle_type | VARCHAR(30) | |
| extra_data | JSONB | default {} |
| current_device_id | UUID | FK → devices.id |
| last_telemetry_id | BIGINT | |
| last_heartbeat | TIMESTAMP | |
| status | VARCHAR(20) | default 'active' |
| created_at | TIMESTAMP | NOT NULL, default now() |
| updated_at | TIMESTAMP | NOT NULL, default now() |

**Table: `devices`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | FK → organizations.id |
| serial_number | VARCHAR(50) | UNIQUE, NOT NULL |
| imei | VARCHAR(20) | UNIQUE |
| device_model | VARCHAR(50) | |
| firmware_version | VARCHAR(20) | |
| api_key | VARCHAR(64) | UNIQUE, NOT NULL |
| status | VARCHAR(20) | default 'offline' |
| created_at | TIMESTAMP | NOT NULL, default now() |
| updated_at | TIMESTAMP | NOT NULL, default now() |

*Note:* The `api_key` is the credential presented in the `X-Device-Key` HTTP header by the physical GPS hardware. It is distinct from user JWT tokens.

**Table: `telemetry`**
| Column | Type | Constraints |
|---|---|---|
| id | BIGINT | PK, auto-increment |
| vehicle_id | UUID | FK → vehicles.id, index |
| device_id | UUID | FK → devices.id |
| latitude | NUMERIC(9,6) | NOT NULL |
| longitude | NUMERIC(9,6) | NOT NULL |
| altitude | FLOAT | |
| speed | FLOAT | |
| course | INTEGER | |
| engine_status | BOOLEAN | |
| odometer | NUMERIC(12,2) | |
| sensors | JSONB | default {} |
| timestamp | TIMESTAMP | NOT NULL, index |
| server_timestamp | TIMESTAMP | NOT NULL |

*Note:* The `sensors` JSONB column allows the hardware payload to include arbitrary sensor readings (e.g., fuel level, door state, battery voltage) without schema migrations.

**Table: `geofences`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | FK → organizations.id |
| name | VARCHAR(100) | NOT NULL |
| fence_type | VARCHAR(20) | 'circle' or 'polygon' |
| geometry | JSONB | NOT NULL |
| speed_limit | INTEGER | nullable |
| is_active | BOOLEAN | NOT NULL, default true |
| notify_on_enter | BOOLEAN | NOT NULL, default true |
| notify_on_exit | BOOLEAN | NOT NULL, default true |
| created_at | TIMESTAMP | NOT NULL, default now() |
| updated_at | TIMESTAMP | NOT NULL, default now() |

*Note:* Geometry is stored as JSONB. Circle fences use `{center: {lat, lng}, radius_m: N}`; polygon fences use a GeoJSON Polygon object. Containment checks are performed in application code using the Haversine formula (circles) and a ray-casting algorithm (polygons) rather than PostGIS spatial queries.

**Table: `alerts`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| organization_id | UUID | FK → organizations.id |
| vehicle_id | UUID | FK → vehicles.id |
| alert_type | VARCHAR(50) | 'geofence', 'speed', 'sos', 'offline' |
| severity | VARCHAR(20) | 'low', 'medium', 'high', 'critical' |
| message | TEXT | |
| extra_data | JSONB | |
| resolved_at | TIMESTAMP | nullable |
| resolved_by | UUID | FK → users.id, nullable |
| created_at | TIMESTAMP | NOT NULL, default now() |
| updated_at | TIMESTAMP | NOT NULL, default now() |

**Table: `device_fcm_tokens`**
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id |
| organization_id | UUID | FK → organizations.id |
| fcm_token | TEXT | UNIQUE, NOT NULL |
| platform | VARCHAR(10) | 'android' or 'ios' |
| created_at | TIMESTAMP | NOT NULL, default now() |
| updated_at | TIMESTAMP | NOT NULL, default now() |

*Note:* A unique constraint on `(user_id, organization_id)` ensures one FCM registration per user per organisation, preventing duplicate push deliveries.

**Table: `audit_logs`**
| Column | Type | Constraints |
|---|---|---|
| id | BIGINT | PK, auto-increment |
| organization_id | UUID | FK → organizations.id, nullable |
| user_id | UUID | FK → users.id, nullable |
| action | VARCHAR(50) | NOT NULL, index |
| target_type | VARCHAR(50) | NOT NULL |
| target_id | VARCHAR(36) | nullable |
| changes | JSONB | |
| ip_address | VARCHAR(45) | |
| user_agent | TEXT | |
| timestamp | TIMESTAMP | NOT NULL, index |

### 3.3.5 Security Module

**Description of Figure 3.6 — Multi-Layered Security Architecture:**
The diagram shows concentric layers. The outermost ring is labelled "Perimeter Security" and contains "TLS 1.3 / HTTPS" and "Nginx Rate Limiting". The next ring is "Application Security" containing "JWT Authentication" and "RBAC Authorisation". The inner ring is "Data Security" containing "bcrypt Password Hashing", "AES-256 Encrypted Backups", and "PostGIS Row-Level Security (RLS)". At the centre is the "Database" cylinder. Arrows show that every request must traverse inward through each layer. A side panel shows "Audit Logging" feeding into a "SIEM / Log Aggregator" for intrusion detection.

**Layer 1 — Transport Security:**
- All client-to-server and device-to-server communication occurs over HTTPS with TLS 1.3.
- Nginx is configured with `ssl_prefer_server_ciphers on`, using only ECDHE + AES-GCM cipher suites.
- HSTS header: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`.
- Certificate pinning is implemented in the Flutter app to prevent man-in-the-middle attacks with rogue certificates.

**Layer 2 — Authentication:**
- JWT access tokens are signed with a 256-bit HMAC secret stored in an environment variable (not in code).
- Token payload contains: `sub` (user ID), `role`, `iat`, `exp`, `jti` (unique token ID).
- Refresh tokens are 128-bit cryptographically random strings, hashed with SHA-256 before storage. Rotation ensures that a stolen refresh token cannot be reused indefinitely.
- The Flutter app stores tokens in `FlutterSecureStorage`, which uses the Android Keystore and iOS Keychain.

**Layer 3 — Authorisation:**
- RBAC is enforced via a custom `@require_role(...)` decorator on Flask routes.
- Example: `@require_role('owner')` on `POST /devices` ensures only owners can register devices.
- Device-level authorisation: a user can only access devices they own or are explicitly assigned to as `driver` or `viewer`. This is enforced by appending `AND (owner_id = :user_id OR EXISTS (SELECT 1 FROM device_shares ...))` to all device queries.

**Layer 4 — Input Validation and Sanitisation:**
- Marshmallow schemas validate all incoming JSON before the request reaches the service layer. Invalid types, out-of-range coordinates, or missing required fields return HTTP 422 with field-level error messages.
- SQL injection is prevented by exclusive use of SQLAlchemy ORM with bound parameters. Raw SQL is never constructed via string interpolation.
- XSS prevention: All user-generated content displayed in the web dashboard is HTML-escaped. The Flutter app renders text via `Text` widgets, which do not interpret HTML.

**Layer 5 — Audit and Monitoring:**
- Every authentication event (login success/failure, token refresh, password reset) is logged to the `audit_logs` table with IP address, user agent, and timestamp.
- Failed login attempts are rate-limited and tracked in Redis. After 10 failures in 5 minutes, the account is temporarily locked for 30 minutes.
- API access logs are shipped to a log aggregator (e.g., Loki or Elasticsearch) for anomaly detection and forensic analysis.

### 3.3.6 System Sequence Diagrams

To illustrate the dynamic behavior of the system, two core workflows are mapped using UML sequence diagrams. These diagrams model the interactions between the mobile client, the backend microservices, the database, and external cloud adapters.

#### 3.3.6.1 User Authentication (Login) Sequence

The User Authentication flow is a two-step verification mechanism designed to authenticate fleet operators and users securely, issue JSON Web Tokens (JWT), and establish a platform-level FCM messaging channel.

**Figure 3.12 — User Authentication Sequence Diagram:**

![User Authentication Sequence Diagram](docs/images/login_sequence.svg)

1. **Step 1 (Credential Submission):** The user provides an email and password in the mobile UI. The client initiates a secure HTTPS POST request to `/auth/login`. The Flask backend verifies the credentials by checking the hash in the PostgreSQL database using `bcrypt`.
2. **OTP Generation & Dispatch:** If valid, the backend generates a random 6-digit OTP, registers its expiration inside the in-memory `_otp_store`, and dispatches an email via SMTP. The backend returns a status flag indicating OTP is required.
3. **Step 2 (OTP Verification):** The user receives the OTP and inputs it in the client UI. The client submits the code to `/auth/verify-otp`.
4. **JWT Session Generation:** The backend validates the code and looks up organization and role privileges in the database. A JWT token containing user claims (`role`, `org_id`, `is_super_admin`) is signed using HS256 and sent back.
5. **FCM Registration:** Upon receiving the token, the client requests its FCM registration token from the OS and uploads it to `/devices/fcm-token` with the client's platform (Android/iOS). The token is saved in PostgreSQL to associate pushing capabilities with the organization.

#### 3.3.6.2 Device Telemetry & Real-Time Tracking Sequence

The Device Telemetry flow tracks physical vehicles in real time. It illustrates the ingestion of location data, database persistence, low-latency client updates via Firebase RTDB, and geofence evaluation with downstream alerting.

**Figure 3.13 — Device Telemetry and Tracking Sequence Diagram:**

![Device Telemetry and Tracking Sequence Diagram](docs/images/device_tracking_sequence.svg)

1. **Telemetry Capture:** The Neo-7M GNSS receiver calculates speed internally by measuring satellite Doppler shifts and formats it inside a standard `$GPRMC` NMEA sentence. The ESP8266 parses these sentences via UART using `TinyGPS++`.
2. **Ingestion Request:** The ESP8266 constructs a telemetry payload and uploads it via HTTPS POST `/api/v1/telemetry` using its unique static device API key (`X-Device-Key`).
3. **Relational Storage & Heartbeat:** The backend authenticates the API key, inserts a new telemetry record in PostgreSQL, and updates the vehicle's `last_heartbeat` and status fields.
4. **Sub-second Location Sync:** To bypass request polling, the backend pushes the GPS state (`lat`, `lng`, `speed`, `heading`, `updatedAt`) directly to Firebase Realtime Database. The active Flutter clients subscribed to `/vehicles/{id}/gps` receive the event and update map markers instantly.
5. **Geofencing & Alerts:** In parallel, the backend retrieves active geofences from PostgreSQL and performs containment calculations (Haversine/ray-casting) and speed limit comparisons.
6. **FCM Dispatch:** If a boundary breach or speed limit violation is detected, an alert record is committed to PostgreSQL, active tenant FCM tokens are retrieved, and a multicast push notification request is pushed to Firebase Cloud Messaging (FCM), which dispatches it to mobile devices.

## 3.4 Database Design

The database design translates the entity-relationship model into a physical PostgreSQL schema optimised for geospatial queries, time-series data, and multi-tenancy. The design priorities are: (i) referential integrity through foreign keys and cascading deletes, (ii) query performance through spatial GiST indexes and time-based partitioning, and (iii) extensibility through JSONB columns for flexible metadata.

### 3.4.1 Database Selection Rationale

PostgreSQL was selected over MySQL and MongoDB for the following reasons:
- **ACID Compliance:** Financial and legal liability associated with vehicle tracking demands strict transactional consistency. All geofence evaluations, alert creations, and telemetry persistence occur within SQLAlchemy sessions that commit atomically, ensuring no partial writes.
- **JSONB Flexibility:** Geofence geometry, vehicle `extra_data`, telemetry sensor readings, and audit change sets are all stored as JSONB, enabling schema-free extensibility without migration scripts for evolving field requirements.
- **Time-Series Scalability:** PostgreSQL 15's declarative partitioning makes the `telemetry` table a natural candidate for monthly partition splits as data volume grows, enabling efficient archival and vacuum without application-layer changes.
- **Spatial Upgrade Path:** While containment checks are currently implemented in application code for simplicity, PostgreSQL supports the PostGIS extension as a zero-migration upgrade path when fleet scale demands sub-millisecond indexed spatial queries.

### 3.4.2 Spatial Query Strategy

Geofence containment is evaluated in the Python application layer rather than via PostGIS extensions, keeping the database dependency footprint to standard PostgreSQL without requiring additional spatial extensions at this stage of the project.

**Figure 3.14 — Geofence Geometric Containment Principles:**

![Geofence Geometric Containment Principles](docs/images/geofence_geometry.svg)

For **circular geofences**, the Haversine formula computes the great-circle distance between the incoming GPS coordinate and the fence centre. If the distance is less than or equal to the configured radius, the vehicle is inside the zone:

```python
R = 6_371_000  # Earth radius in metres
a = sin(Δlat/2)² + cos(lat1)·cos(lat2)·sin(Δlng/2)²
distance = R · 2 · atan2(√a, √(1−a))
is_inside = distance <= radius_m
```

For **polygon geofences**, a ray-casting algorithm determines whether the GPS point is inside a GeoJSON polygon ring. A ray is cast from the test point along the positive x-axis; the number of ring-edge crossings determines inside/outside status (odd = inside, even = outside).

**Figure 3.15 — UML Activity Diagram for Geofence Containment Check:**

![UML Activity Diagram for Geofence Containment Check](docs/images/geofence_activity.svg)

The programmatic logic of these checks is structured inside [utils.py](file:///home/juniorbesong/work/tieftechnologiesltd/car-tracking-platform/backend/api/utils/utils.py). Upon every incoming telemetry point, the system queries the active fences list and runs `vehicle_in_geofence()`. If the geofence type is a circle, the Haversine distance is evaluated. If it is a polygon, the ray-casting loop counts boundary crossings: if the crossing count is odd, the vehicle is marked inside.

Geofence geometry is stored as JSONB in the `geofences` table, giving the schema flexibility to evolve without migration scripts. Future scaling to PostGIS `ST_Within` and GiST spatial indexes is architecturally straightforward because the geometry representation already follows GeoJSON conventions.

### 3.4.3 Data Retention and Archival

- **Waypoints:** Retained for 90 days in hot partitions. After 90 days, partitions are detached and compressed into Parquet files stored in object storage (e.g., AWS S3 or MinIO) for long-term analytics.
- **Alerts:** Retained for 90 days in the primary database. A nightly cron job deletes expired alerts in batches of 1,000 to avoid table bloat.
- **Audit Logs:** Retained for 365 days in the database, then archived to cold storage.
- **Refresh Tokens:** Automatically purged 7 days after creation by a PostgreSQL `pg_cron` scheduled task.

### 3.4.4 Backup and Recovery

- **WAL Archiving:** PostgreSQL continuous archiving is enabled to a secure backup server, allowing point-in-time recovery (PITR) to any moment within the retention window.
- **Daily pg_dump:** A full logical backup runs at 02:00 UTC, encrypted with AES-256 and uploaded to off-site storage.
- **Disaster Recovery:** The Recovery Time Objective (RTO) is 4 hours; the Recovery Point Objective (RPO) is 15 minutes (bounded by WAL archive frequency).

## 3.5 User Interface Design

The user interface design follows Material Design 3 principles for Android and Human Interface Guidelines for iOS, unified through Flutter's adaptive theming. The design prioritises clarity, situational awareness, and minimal interaction latency for safety-critical tasks such as geofence breach response.

### 3.5.1 Login and Onboarding Screens

**Description of Figure 3.7 — Login and Onboarding Wireframes:**
The wireframe shows two smartphone screens side by side. Screen 1 (Login) displays the app logo at top centre, followed by two text fields (Email, Password) with rounded corners and floating labels. A primary "Sign In" button in brand blue sits below. A "Forgot Password?" text link and "Create Account" outlined button are at the bottom. Screen 2 (Onboarding) shows a three-step carousel: Step 1 illustrates a map with a car icon ("Track Your Vehicle"); Step 2 shows a fence icon ("Set Safe Zones"); Step 3 shows a bell icon ("Get Instant Alerts"). A "Get Started" button appears after the third step.

**Design Rationale:**
- The login screen uses a single-column layout to accommodate narrow phone screens (320 dp width).
- Password fields toggle visibility via an eye icon, reducing input errors.
- Biometric authentication (fingerprint/face) is offered after the first successful login via `local_auth` plugin.

### 3.5.2 Dashboard (Map) Screen

**Description of Figure 3.8 — Dashboard Map Screen Wireframe:**
The wireframe shows a full-screen Google Map occupying 100% of the viewport. At the top, a search bar reads "Search location...". Below it, a horizontal chip row shows filter options: "All Vehicles", "Car 1", "Car 2". The vehicle marker is a custom car icon rotated to match heading. A semi-transparent bottom sheet (draggable upward) shows: vehicle name, current speed (62 km/h), address reverse-geocoded from coordinates, and three action buttons ("History", "Geofences", "Alerts"). A floating action button (FAB) in the bottom-right corner toggles between normal map view and satellite imagery.

**Design Rationale:**
- The map is the primary information surface; all other controls are secondary and collapsible.
- Speed is displayed in a large, high-contrast font (32 sp) with colour coding: green for normal, amber for warning, red for overspeed.
- The bottom sheet uses `DraggableScrollableSheet` to reveal more details (satellite count, battery voltage, last update time) when dragged to 75% screen height.
- Clustering is enabled when zoomed out to prevent marker overlap for fleet views.

### 3.5.3 Geofence Creation Screen

**Description of Figure 3.9 — Geofence Editor Wireframe:**
The wireframe shows a map with a semi-transparent blue circle centred on a dropped pin. A slider at the bottom adjusts radius from 100 m to 5,000 m in 100 m steps. Above the slider, a segmented control switches between "Circle" and "Polygon". In polygon mode, the circle disappears and a blue polygon with draggable vertex handles is shown. A text field at the top allows naming the geofence (e.g., "Home"). A schedule toggle enables time-based activation; when on, two time pickers appear for Start and End. Primary buttons at the bottom are "Save" (enabled when valid) and "Cancel".

**Design Rationale:**
- Direct manipulation on the map (tap to drop pin, drag to move) is more intuitive than coordinate entry.
- Real-time validation: if the polygon self-intersects, the shape turns red and a snackbar warns "Invalid polygon: edges must not cross."
- The schedule feature is collapsed by default to reduce cognitive load for simple always-on geofences.

### 3.5.4 Alert Inbox and Notification UI

**Description of Figure 3.10 — Alert Inbox Wireframe:**
The wireframe shows a scrollable list of alert cards. Each card has a left icon (green circle with arrow for entry, red circle with arrow for exit, orange triangle for overspeed), a title ("Car 1 entered Home"), a subtitle with timestamp ("Today, 08:42 AM"), and a right chevron. Unread cards have a light blue background tint. A filter icon in the app bar opens a bottom sheet with checkboxes for alert types. A "Mark All Read" text button sits in the app bar overflow menu.

**Design Rationale:**
- Icons and colour coding allow at-a-glance triage without reading text.
- Swipe gestures (dismiss, mark read) follow platform conventions (iOS: swipe left; Android: swipe right).
- Deep-linking ensures that tapping an alert opens the map centred on the event location with a temporary pulsing ring animation for 5 seconds.

### 3.5.5 History Replay Screen

**Description of Figure 3.11 — History Player Wireframe:**
The wireframe shows a map with a completed grey route polyline and a blue progress polyline that animates from start to finish. Below the map, a control panel contains: a date range picker ("May 1 – May 7"), a playback speed toggle (1×, 2×, 4×), a play/pause button, and a progress slider. Stop points are marked as red circles along the route; tapping a circle opens an info card showing arrival time, departure time, and dwell duration. A summary bar at the bottom displays: total distance ("142 km"), max speed ("89 km/h"), and total stops ("12").

**Design Rationale:**
- Playback animation uses `AnimationController` with linear interpolation over the route polyline points.
- The progress slider allows scrubbing to any point in time, updating the vehicle marker position and speed display instantaneously.
- Export buttons (GPX, CSV, Share) are accessible via an app bar action icon.

## 3.6 System Security Design

Security is not a peripheral concern but a first-class design constraint woven into every layer of the system. The security design follows the defence-in-depth principle: no single mechanism is relied upon exclusively; instead, multiple independent controls overlap to protect assets (vehicle location data, user credentials, and system availability) against diverse threat vectors.

### 3.6.1 Threat Model

The following threat actors and vectors were identified during the design phase:

- **Threat Actor A — Opportunistic Attacker:** Scans for open APIs, attempts credential stuffing, or exploits known vulnerabilities in dependencies. Motivation: data theft, account takeover.
- **Threat Actor B — Network Eavesdropper:** Intercepts traffic on public Wi-Fi or cellular networks. Motivation: tracking vehicle movements for burglary or kidnapping.
- **Threat Actor C — Malicious Insider:** A `viewer` or `driver` attempts to escalate privileges to `owner` or access unauthorised devices. Motivation: financial gain, stalking.
- **Threat Actor D — Denial-of-Service (DoS) Actor:** Floods the API with requests to degrade service. Motivation: disruption, extortion.

### 3.6.2 Countermeasures by Threat Vector

**Against Credential Stuffing and Brute Force:**
- Passwords are hashed with bcrypt (cost factor 12), making offline cracking computationally expensive.
- Login rate limiting (10 attempts per 5 minutes per username) prevents automated guessing.
- Account lockout after repeated failures notifies the user via email.
- Registration rejects passwords found in common breach databases (Have I Been Pwned API integration).

**Against Network Eavesdropping and Man-in-the-Middle:**
- TLS 1.3 with perfect forward secrecy (ECDHE) ensures that even if the server's private key is compromised, past sessions cannot be decrypted.
- Certificate pinning in the Flutter app prevents acceptance of fraudulent certificates issued by compromised CAs.
- Device-to-server telemetry uses HTTPS; no fallback to HTTP is permitted. The firmware validates the server's certificate against a bundled CA root.

**Against Privilege Escalation and Unauthorised Data Access:**
- RBAC decorators enforce role checks at the API gateway level, not just the UI level.
- Row-Level Security (RLS) policies on PostgreSQL tables ensure that even if an SQL query is crafted to bypass the application layer, the database will only return rows owned by the current user.
- Example RLS policy on `devices`:
  ```sql
  CREATE POLICY device_owner_isolation ON devices
  FOR ALL TO application_user
  USING (owner_id = current_setting('app.current_user_id')::UUID);
  ```

**Against Denial-of-Service:**
- Nginx rate limiting (100 req/min per IP) drops excessive requests before they reach the application server.
- API-level rate limiting (per-user token bucket) protects against authenticated abuse.
- Database connection pooling prevents resource exhaustion from slow queries. A query timeout of 5 seconds kills long-running requests.
- The `waypoints` bulk upload endpoint rejects payloads exceeding 500 records to prevent memory exhaustion.

### 3.6.3 Data Privacy and Compliance

- **Data Minimisation:** The system collects only necessary telemetry (location, speed, satellite count). No audio, video, or OBD diagnostic data is captured.
- **Consent:** During registration, users explicitly consent to location tracking and data storage. The privacy policy is linked in the app and backend.
- **Right to Deletion:** Users can request full account deletion, which cascades to remove all personal data, devices, and waypoints within 30 days as per GDPR-inspired principles.
- **Encryption at Rest:** PostgreSQL data files reside on an encrypted volume (LUKS). Backups are encrypted with AES-256-GCM before leaving the server.
- **Audit Trail:** All data access and modification events are logged with user ID, timestamp, and IP address, enabling forensic investigation in case of breach.

### 3.6.4 Security Testing Strategy

The security design is validated through:
- **Static Analysis:** `bandit` scans Python code for common vulnerabilities (hardcoded secrets, SQL injection patterns, weak crypto).
- **Dependency Scanning:** `safety` and `pip-audit` check for known CVEs in Python packages. `flutter_security` and `dependabot` monitor Dart dependencies.
- **Penetration Testing:** Manual testing using OWASP ZAP to identify XSS, CSRF, and injection vectors. API fuzzing with `schemathesis` to discover edge-case validation failures.
- **Firmware Security:** The ESP8266 firmware is compiled with `-fno-exceptions` and stack protection. Over-the-air (OTA) updates, if implemented, will be signed with ECDSA to prevent malicious firmware flashing.

---

## REFERENCES

[1] L. Atzori, A. Iera, and G. Morabito, "The Internet of Things: A survey," *Computer Networks*, vol. 54, no. 15, pp. 2787–2805, 2010.

[2] u-blox AG, *NEO-7 Data Sheet*, UBX-13003830, Thalwil, Switzerland, 2014.

[3] Espressif Systems, *ESP8266 Technical Reference Manual*, Version 1.4, Shanghai, China, 2024.

[4] Google LLC, "Flutter architectural overview," 2024. [Online]. Available: https://docs.flutter.dev/resources/architectural-overview

[5] P. Soares, "Bloc: Business Logic Component," 2018. [Online]. Available: https://bloclibrary.dev

[6] A. Ronacher, *Flask Documentation*, Release 2.3, 2010. [Online]. Available: https://flask.palletsprojects.com

[7] B. Kummamuru, "Real time GPS location tracker using ESP8266," *SSRN Electronic Journal*, 2021.

[8] B. Cahyadi and K. Edistira, "Motor vehicle tracking and security technology using GPS u-blox NEO 6M based on Android application," in *Proc. 4th Int. Conf. Inf. Technol. Security*, 2023.

[9] O. A. Ibrahim Mohamed *et al.*, "AIN Tracking System: GPS-based real-time vehicle tracking," Ain Shams University, Cairo, Egypt, Graduation Project, 2024. [Online]. Available: https://github.com/ibrahimmohamedkmal/AIN-Tracking-System-GPS-Based-Real-Time-Vehicle-Tracking

[10] N. D. Wahyu, "Sistem keamanan kendaraan jarak jauh menggunakan GPS Neo-6M dan NodeMCU ESP8266," *J. Informatika dan Komputer*, vol. 16, no. 2, pp. 112–120, 2024.

[11] P. Dhumal, M. Sangewar, S. Sawantbhonsale, and S. Nandan, "Auto Shield: A review on smart vehicle theft detection strategies," *Int. J. Novel Res. Development*, vol. 10, no. 4, pp. 337–343, 2025.

[12] N. N. Hlaing, M. Naing, and S. S. Naing, "GPS and GSM based vehicle tracking system," *Int. J. Trend Sci. Res. Development*, vol. 3, no. 4, pp. 271–275, 2019.

[13] u-blox AG, *NEO Modules TCXO-to-Crystal Migration Guide*, UBX-21003407, Thalwil, Switzerland, 2021.

[14] B. Wukkadada and A. Fernandes, "Vehicle tracking system using GSM and GPS technologies," *IOSR J. Comput. Eng.*, vol. 19, no. 1, pp. 05–08, 2017.

[15] IEEE, *IEEE Recommended Practice for Software Requirements Specifications*, IEEE Std 830-1998, 1998.
