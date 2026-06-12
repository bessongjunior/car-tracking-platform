# Database Architecture Documentation

This document describes the high-level database architecture for the Car Tracking Platform. The schema is designed for scalability, multi-tenancy, and high-frequency telemetry data processing.

## Architectural Highlights

### 1. Multi-Tenancy & Role-Based Access Control (RBAC)
- **Multi-Organization Support**: Users are decoupled from organizations via an `OrganizationMember` association table. This allows a single user account to belong to multiple organizations (e.g., a contractor managing fleets for different companies).
- **Granular Roles**: Roles ('admin', 'user') are defined per membership. A user can be an 'admin' in one organization and a standard 'user' in another.
- **Super Admin**: A global `is_super_admin` flag on the `User` table allows for system-wide administrative access. Super admins do not need to be members of an organization to manage the platform.
- **Data Isolation**: All core assets (`Vehicle`, `Device`, `Geofence`, `Alert`) are strictly tied to an `Organization` ID to ensure total data isolation between tenants.

### 2. Decoupled Hardware (`Device` vs `Vehicle`)
- **Purpose**: Flexibility and historical integrity.
- **Details**: GPS tracking hardware (`Device`) is decoupled from the asset being tracked (`Vehicle`). In real-world fleet management, devices are frequently swapped between vehicles. This schema allows a device to be unlinked and reassigned without losing the tracking history of the vehicle.

### 3. Advanced Telemetry (`JSONB` & `Numeric`)
- **Precision**: We use `Numeric(9,6)` for latitude and longitude, providing sub-meter precision for global positioning.
- **Extensibility**: PostgreSQL-specific `JSONB` fields are used for `sensors` and `metadata`. This allows the system to support diverse hardware and sensor types (fuel level, door status, engine temperature, etc.) without requiring schema migrations for every new device capability.

### 4. Performance Denormalization
- **Strategy**: Dashboards often need the "current" state of all assets.
- **Details**: The `Vehicle` table denormalizes `last_telemetry_id` and `current_device_id`. This significantly improves performance for real-time fleet overview screens by avoiding heavy joins against the massive `telemetry` history table.

### 5. Auditability (`TimestampMixin`)
- **Purpose**: Transparency and debugging.
- **Details**: Every entity in the system inherits from a `TimestampMixin`, ensuring that `created_at` and `updated_at` fields are automatically managed.

### 6. Extensible Geofencing & Alerts
- **Geofencing**: The `Geofence` table stores geometry data as `JSONB` (GeoJSON compatible), allowing for both simple circular fences and complex polygons.
- **Alerting**: A robust `Alert` system tracks event-driven triggers like overspeeding, SOS signals, or geofence boundary crossings.

### 7. Comprehensive Audit Trails (`AuditLog`)
- **Immutable History**: Tracks every significant administrative and security action.
- **Contextual Data**: Captures not just the change (old vs new state in `JSONB`), but also the `ip_address`, `user_agent`, and the specific `Organization` context.
- **Scalability**: Uses `BigInteger` for the primary key to handle millions of audit entries over time without overflow.
- **Security**: Essential for identifying the source of unauthorized changes or investigating system anomalies.

---

## Entity Relationship Summary

- **Organization**: The root container for all assets and users.
- **User**: Managed within an organization with role-based access.
- **Vehicle**: The primary asset; linked to an organization.
- **Device**: The tracking hardware; assigned to a vehicle but independently managed.
- **Telemetry**: Time-series data points (GPS, speed, sensors) linked to both a vehicle and a device.
- **Geofence**: Defined areas for monitoring vehicle entry/exit.
- **Alert**: Notifications generated based on telemetry events.
