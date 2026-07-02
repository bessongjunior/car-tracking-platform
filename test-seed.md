# CarTracker Demo Seed — Buea, Cameroon

Run once after setting up the database:
```bash
cd backend
source venv/bin/activate
python seed.py
```

---

## User Credentials

| Role    | Email                              | Password    |
|---------|------------------------------------|-------------|
| Admin   | admin@tieftechnologiesltd.com      | Admin@1234  |
| Manager | manager@tieftechnologiesltd.com    | Fleet@2024  |

Login flow: enter email + password → receive OTP (check server log or Gmail) → enter OTP → JWT issued.

---

## Organisation

| Field | Value                  |
|-------|------------------------|
| Name  | Tief Technologies Ltd  |
| Slug  | tief-tech-bu           |

---

## Vehicles

| Name        | Plate      | VIN               | Type    | Status |
|-------------|------------|-------------------|---------|--------|
| Hilux-01    | SW 1234 A  | 1HTMMAAJ0AH123456 | pickup  | active |
| Sprinter-03 | SW 5678 B  | WD3PF4CC4A5234567 | van     | active |
| Actros-09   | SW 9012 C  | WDB9630351L345678 | truck   | active |

Plates use Cameroon Southwest Region format (`SW XXXX Y`).

---

## GPS Device

| Field         | Value                  |
|---------------|------------------------|
| Serial        | GPS-BU-001             |
| IMEI          | 352999001234567        |
| Model         | Teltonika FMB920       |
| Firmware      | 03.25.07               |
| API Key       | dev-bu-gps-001         |
| Assigned to   | Hilux-01               |

Send telemetry via:
```bash
curl -X POST http://192.168.1.152:5000/api/v1/telemetry \
  -H "X-Device-Key: dev-bu-gps-001" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 4.1566, "longitude": 9.2425, "speed": 45, "course": 225}'
```

---

## Geofences

| Name               | Type   | Center (lat, lng)      | Radius | Speed Limit | Enter | Exit |
|--------------------|--------|------------------------|--------|-------------|-------|------|
| City of Buea       | circle | 4.1566, 9.2425         | 3000 m | 60 km/h     | yes   | yes  |
| University of Buea | circle | 4.1490, 9.2365         | 300 m  | —           | yes   | yes  |
| Buea Town Center   | circle | 4.1537, 9.2417         | 400 m  | 60 km/h     | no    | yes  |

**City of Buea** covers the entire city (Mile 17 → Great Soppo, ~6 km diameter) and is the primary geofence for Hilux-01.

---

## Telemetry Routes (historical seed points)

### Hilux-01 — Molyko → UB Campus (2 hours ago)

| # | Lat     | Lng    | Speed    | Heading | Location           |
|---|---------|--------|----------|---------|--------------------|
| 1 | 4.1574  | 9.2513 | 45 km/h  | 225°    | Molyko Junction    |
| 2 | 4.1551  | 9.2478 | 52 km/h  | 225°    | Molyko (mid)       |
| 3 | 4.1527  | 9.2447 | 48 km/h  | 225°    | Mid-route          |
| 4 | 4.1510  | 9.2410 | 38 km/h  | 270°    | Approaching UB     |
| 5 | 4.1490  | 9.2365 | 0 km/h   | 270°    | UB Campus (parked) |

### Sprinter-03 — Buea Town → Great Soppo (1 hour ago)

| # | Lat     | Lng    | Speed    | Heading | Location       |
|---|---------|--------|----------|---------|----------------|
| 1 | 4.1537  | 9.2417 | 35 km/h  | 180°    | Buea Town      |
| 2 | 4.1460  | 9.2390 | 42 km/h  | 180°    | Heading south  |
| 3 | 4.1388  | 9.2293 | 0 km/h   | 180°    | Great Soppo    |

### Actros-09 — Parked at Mile 17 (30 min ago)

| # | Lat     | Lng    | Speed  | Heading | Location |
|---|---------|--------|--------|---------|----------|
| 1 | 4.1717  | 9.2597 | 0 km/h | 0°      | Mile 17  |

---

## Sample Alerts

| Vehicle     | Type     | Severity | Message                                          |
|-------------|----------|----------|--------------------------------------------------|
| Hilux-01    | geofence | medium   | SW 1234 A entered zone "City of Buea"            |
| Sprinter-03 | geofence | medium   | SW 5678 B exited zone "Buea Town Center"         |
| Actros-09   | offline  | critical | SW 9012 C signal lost — last seen Mile 17        |

---

## Firebase RTDB Structure (written by telemetry ingest)

```
/vehicles/{vehicle_id}/
  gps:
    lat:       4.1490
    lng:       9.2365
    heading:   270
    speed:     0
    updatedAt: <unix ms>
  meta:
    plate:  "SW 1234 A"
    status: "online"
```

---

## Map Bounds

All seed coordinates fall within:

```
SW corner: 4.1388, 9.2293  (Great Soppo)
NE corner: 4.1717, 9.2597  (Mile 17)
```

Centre the map on **4.1566, 9.2425** at zoom 14 to see all vehicles.
