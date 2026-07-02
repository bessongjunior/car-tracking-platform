#!/usr/bin/env python3
"""
One-shot database seeder for CarTracker demo — Buea, Cameroon.
Run: cd backend && source venv/bin/activate && python seed.py
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, '.')

from api import create_app
from api.models.models import (
    Alert, Device, Geofence, Organization,
    OrganizationMember, Telemetry, User, Vehicle, db,
)
from api.services.services import AuthService


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Buea, Cameroon ─────────────────────────────────────────────────────────────

VEHICLES = [
    {'name': 'Hilux-01',    'license_plate': 'SW 1234 A', 'vin': '1HTMMAAJ0AH123456', 'vehicle_type': 'pickup'},
    {'name': 'Sprinter-03', 'license_plate': 'SW 5678 B', 'vin': 'WD3PF4CC4A5234567', 'vehicle_type': 'van'},
    {'name': 'Actros-09',   'license_plate': 'SW 9012 C', 'vin': 'WDB9630351L345678', 'vehicle_type': 'truck'},
]

# Hilux-01: Molyko Junction → UB Campus
HILUX_ROUTE = [
    (4.1574, 9.2513, 45.0, 225),   # Molyko Junction
    (4.1551, 9.2478, 52.0, 225),   # Molyko (mid)
    (4.1527, 9.2447, 48.0, 225),   # Mid-route
    (4.1510, 9.2410, 38.0, 270),   # Approaching UB
    (4.1490, 9.2365,  0.0, 270),   # UB Campus (parked)
]

# Sprinter-03: Buea Town → Great Soppo
SPRINTER_ROUTE = [
    (4.1537, 9.2417, 35.0, 180),   # Buea Town Center
    (4.1460, 9.2390, 42.0, 180),   # Heading south
    (4.1388, 9.2293,  0.0, 180),   # Great Soppo (parked)
]

# Actros-09: Parked at Mile 17
ACTROS_ROUTE = [
    (4.1717, 9.2597, 0.0, 0),      # Mile 17
]

GEOFENCES = [
    {
        # Large zone covering the whole city — Hilux primary geofence
        'name': 'City of Buea',
        'fence_type': 'circle',
        'geometry': {'center': {'lat': 4.1566, 'lng': 9.2425}, 'radius': 3000},
        'speed_limit': 60,
        'notify_on_enter': True,
        'notify_on_exit': True,
    },
    {
        'name': 'University of Buea',
        'fence_type': 'circle',
        'geometry': {'center': {'lat': 4.1490, 'lng': 9.2365}, 'radius': 300},
        'speed_limit': None,
        'notify_on_enter': True,
        'notify_on_exit': True,
    },
    {
        'name': 'Buea Town Center',
        'fence_type': 'circle',
        'geometry': {'center': {'lat': 4.1537, 'lng': 9.2417}, 'radius': 400},
        'speed_limit': 60,
        'notify_on_enter': False,
        'notify_on_exit': True,
    },
]


def seed():
    app = create_app()
    with app.app_context():
        print('⏳  Seeding database …\n')

        # ── Organisation ──────────────────────────────────────────────────────
        org = Organization.query.filter_by(slug='tief-tech-bu').first()
        if not org:
            org = Organization(name='Tief Technologies Ltd', slug='tief-tech-bu')
            db.session.add(org)
            db.session.flush()
            print(f'✓  Organisation: {org.name}')
        else:
            print(f'·  Organisation exists: {org.name}')

        # ── Users ─────────────────────────────────────────────────────────────
        users_seed = [
            ('Brice Admin Besong', 'admin@tieftechnologiesltd.com',   'Admin@1234', 'admin',   True),
            ('Junior Besong',      'ndipivan109@gmail.com', 'Fleet@2024', 'manager', False),
        ]
        user_objs = []
        for full_name, email, password, role, is_super in users_seed:
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    email=email,
                    password_hash=AuthService.hash_password(password),
                    full_name=full_name,
                    is_super_admin=is_super,
                    is_active=True,
                )
                db.session.add(user)
                db.session.flush()
                db.session.add(OrganizationMember(
                    user_id=user.id, organization_id=org.id, role=role,
                ))
                print(f'✓  User: {email}  /  {password}  [{role}]')
            else:
                from api.models.models import OrganizationMember as OM
                if not OM.query.filter_by(user_id=user.id, organization_id=org.id).first():
                    db.session.add(OM(user_id=user.id, organization_id=org.id, role=role))
                print(f'·  User exists: {email}')
            user_objs.append(user)

        db.session.commit()

        # ── Vehicles ──────────────────────────────────────────────────────────
        vehicle_objs = []
        for v in VEHICLES:
            vehicle = Vehicle.query.filter_by(license_plate=v['license_plate']).first()
            if not vehicle:
                vehicle = Vehicle(
                    organization_id=org.id,
                    name=v['name'],
                    license_plate=v['license_plate'],
                    vin=v['vin'],
                    vehicle_type=v['vehicle_type'],
                    status='active',
                    last_heartbeat=_now(),
                )
                db.session.add(vehicle)
                db.session.flush()
                print(f'✓  Vehicle: {v["name"]}  ({v["license_plate"]})')
            else:
                print(f'·  Vehicle exists: {v["name"]}')
            vehicle_objs.append(vehicle)

        db.session.commit()

        # ── GPS Device (assigned to Hilux-01) ─────────────────────────────────
        hilux = vehicle_objs[0]
        device = Device.query.filter_by(serial_number='GPS-BU-001').first()
        if not device:
            device = Device(
                organization_id=org.id,
                serial_number='GPS-BU-001',
                imei='352999001234567',
                device_model='Teltonika FMB920',
                firmware_version='03.25.07',
                api_key='dev-bu-gps-001',
                status='online',
            )
            db.session.add(device)
            db.session.flush()
            hilux.current_device_id = device.id
            db.session.commit()
            print(f'✓  Device: GPS-BU-001  (api_key: dev-bu-gps-001)  → {hilux.name}')
        else:
            print(f'·  Device exists: GPS-BU-001')

        # ── Geofences ─────────────────────────────────────────────────────────
        for gf in GEOFENCES:
            if not Geofence.query.filter_by(name=gf['name'], organization_id=org.id).first():
                db.session.add(Geofence(
                    organization_id=org.id,
                    name=gf['name'],
                    fence_type=gf['fence_type'],
                    geometry=gf['geometry'],
                    speed_limit=gf.get('speed_limit'),
                    notify_on_enter=gf['notify_on_enter'],
                    notify_on_exit=gf['notify_on_exit'],
                    is_active=True,
                ))
                print(f'✓  Geofence: {gf["name"]}')
            else:
                print(f'·  Geofence exists: {gf["name"]}')

        db.session.commit()

        # ── Telemetry ─────────────────────────────────────────────────────────
        routes = [
            (vehicle_objs[0], device, HILUX_ROUTE,    timedelta(hours=2),    1456.0, 24300.0, 78),
            (vehicle_objs[1], device, SPRINTER_ROUTE, timedelta(hours=1),    1462.0, 51200.0, 62),
            (vehicle_objs[2], device, ACTROS_ROUTE,   timedelta(minutes=30), 1471.0, 89100.0, 45),
        ]
        for vehicle, dev, route, offset, alt, odo_base, fuel_base in routes:
            if Telemetry.query.filter_by(vehicle_id=vehicle.id).count() == 0:
                base_time = _now() - offset
                for i, (lat, lng, speed, course) in enumerate(route):
                    db.session.add(Telemetry(
                        vehicle_id=vehicle.id,
                        device_id=dev.id,
                        latitude=lat,
                        longitude=lng,
                        altitude=alt,
                        speed=speed,
                        course=course,
                        engine_status=speed > 0,
                        odometer=odo_base + i * 1.4,
                        sensors={'fuel_level': fuel_base - i * 2},
                        timestamp=base_time + timedelta(minutes=i * 9),
                        server_timestamp=_now(),
                    ))
                db.session.commit()
                print(f'✓  Telemetry: {len(route)} points for {vehicle.name}')
            else:
                print(f'·  Telemetry exists for {vehicle.name}')

        # ── Sample Alerts ─────────────────────────────────────────────────────
        if Alert.query.filter_by(organization_id=org.id).count() == 0:
            hilux, sprinter, actros = vehicle_objs
            alerts = [
                Alert(
                    organization_id=org.id,
                    vehicle_id=hilux.id,
                    alert_type='geofence',
                    severity='medium',
                    message=f'{hilux.license_plate} entered zone "City of Buea"',
                    extra_data={'zone': 'City of Buea', 'event': 'entered'},
                ),
                Alert(
                    organization_id=org.id,
                    vehicle_id=sprinter.id,
                    alert_type='geofence',
                    severity='medium',
                    message=f'{sprinter.license_plate} exited zone "Buea Town Center"',
                    extra_data={'zone': 'Buea Town Center', 'event': 'exited'},
                ),
                Alert(
                    organization_id=org.id,
                    vehicle_id=actros.id,
                    alert_type='offline',
                    severity='critical',
                    message=f'{actros.license_plate} signal lost — last seen Mile 17',
                    extra_data={'last_lat': 4.1717, 'last_lng': 9.2597},
                ),
            ]
            for a in alerts:
                db.session.add(a)
            db.session.commit()
            print(f'✓  Alerts: {len(alerts)} sample alerts')
        else:
            print(f'·  Alerts exist')

        print('\n🎉  Seed complete!\n')
        print('  Credentials:')
        print('  admin@tieftechnologiesltd.com    /  Admin@1234')
        print('  ndipivan109@gmail.com            /  Fleet@2024\n')
        print('  GPS device API key:  dev-bu-gps-001')
        print('  Header:  X-Device-Key: dev-bu-gps-001')


if __name__ == '__main__':
    seed()
