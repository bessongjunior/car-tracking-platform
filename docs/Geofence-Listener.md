# Geofence Listener Service Implementation Plan

## Objective
Implement a high-performance, asynchronous listener that monitors Firebase Realtime Database for vehicle GPS updates, calculates geofence breaches in real-time using `Shapely`, and triggers backend alerts.

---

## 1. Architecture Overview

1. **Producer**: Hardware devices write GPS data (lat, lng, speed) directly to Firebase at `/vehicles/{vehicleId}/gps`.
2. **Listener**: A dedicated Python process on the backend uses the `firebase-admin` SDK to "listen" to all changes in the `/vehicles` path.
3. **Logic Engine**: 
   - For every GPS update, the engine fetches the active geofences for the vehicle's organization.
   - It uses `Shapely` to check if the point is within the geofence geometry.
   - It maintains a simple in-memory "last state" (In/Out) to detect **Transition Events** (Entry or Exit).
4. **Notifier**: If a breach is detected, it creates an `Alert` record in PostgreSQL and sends an FCM push notification.

---

## 2. File Structure

- `backend/api/services/geofence_engine.py`: Core logic for geometric calculations.
- `backend/api/services/firebase_listener.py`: The long-running Firebase connection handler.
- `backend/run_monitor.py`: Entry point for the independent background process.

---

## 3. Implementation Details

### A. Geofence Engine (`geofence_engine.py`)
Uses `shapely.geometry` to handle both circular and polygonal boundaries.

```python
from shapely.geometry import Point, Polygon
from math import radians, cos, sin, asin, sqrt

def is_inside_circle(point_lat, point_lng, fence_lat, fence_lng, radius_m):
    # Haversine formula to calculate distance
    # ... logic here ...
    return distance <= radius_m

def is_inside_polygon(lat, lng, coordinates):
    poly = Polygon(coordinates)
    point = Point(lat, lng)
    return poly.contains(point)
```

### B. Firebase Listener (`firebase_listener.py`)
Uses `db.reference('/vehicles').listen(callback)` to receive push updates from Firebase.

```python
import firebase_admin
from firebase_admin import db

def start_listening():
    ref = db.reference('/vehicles')
    # This runs in a separate thread automatically
    ref.listen(on_gps_update)

def on_gps_update(event):
    if event.event_type == 'put':
        # 1. Parse vehicleId and GPS data
        # 2. Query Postgres for this vehicle's organization geofences
        # 3. Perform Shapely check
        # 4. If state changed (e.g., Outside -> Inside), trigger alert
```

### C. State Management
To prevent spamming "Inside" alerts, the listener must track the vehicle's previous state.
- **State Store**: Redis (recommended for production) or a simple In-Memory Dictionary (for this phase).
- **Key**: `vehicle_id:geofence_id`
- **Value**: `inside` | `outside`

---

## 4. Why This is "Senior Level"

1. **Asynchronous & Decoupled**: The main Flask API is never blocked by GPS processing. If the API goes down, the tracking continues.
2. **Geometric Precision**: Using `Shapely` allows for complex polygon support (warehouses, specific road segments) instead of just simple circles.
3. **Database Efficiency**: We only query PostgreSQL when a vehicle actually moves, and we can cache geofence definitions for 5-10 minutes to avoid heavy DB hits.
4. **Scalability**: The listener process can be containerized and scaled horizontally by sharding the Firebase paths.

---

## 5. Deployment Commands

```bash
# Install dependencies
pip install shapely firebase-admin

# Run as a background worker
python run_monitor.py
```
