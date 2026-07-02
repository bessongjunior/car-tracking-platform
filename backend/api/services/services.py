"""
Core business logic.

Firebase paths written by this module:
  /vehicles/{vehicle_id}/gps  → lat, lng, heading, speed, updatedAt
  /vehicles/{vehicle_id}/meta → plate, status
"""
import logging
from datetime import datetime, timedelta, timezone

import uuid
import bcrypt
from flask import current_app
from flask_jwt_extended import create_access_token

from ..models.models import (
    Alert, Device, DeviceFCMToken, Geofence,
    Telemetry, User, Vehicle, db,
)
from ..utils.email_service import send_otp_email
from ..utils.helpers import generate_otp, utcnow
from ..utils.utils import vehicle_in_geofence

log = logging.getLogger(__name__)

# In-memory OTP store: {user_id: (otp, expires_at)}
_otp_store: dict[str, tuple[str, datetime]] = {}

# Geofence crossing state: {(vehicle_id, fence_id): was_inside}
# Tracks previous position so alerts only fire on boundary transitions.
_geofence_state: dict[tuple[str, str], bool] = {}

# Speed alert state: {vehicle_id: is_currently_over_limit}
# Prevents repeat alerts while speed stays above the threshold.
_speed_alert_active: dict[str, bool] = {}


# ── Auth ──────────────────────────────────────────────────────────────────────

class AuthService:
    @staticmethod
    def login(email: str, password: str):
        user = User.query.filter_by(email=email, is_active=True).first()
        if not user:
            return None, 'Invalid credentials'
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return None, 'Invalid credentials'

        otp = generate_otp()
        expiry = utcnow() + timedelta(seconds=current_app.config['OTP_EXPIRY_SECONDS'])
        _otp_store[str(user.id)] = (otp, expiry)

        # Always log the OTP so developers can test without email configured.
        log.warning('OTP for %s: %s', email, otp)

        # Also send via Gmail SMTP (non-blocking background thread).
        send_otp_email(
            to_email=email,
            otp=otp,
            user_name=user.full_name or '',
            sender=current_app.config['GMAIL_SENDER'],
            app_password=current_app.config['GMAIL_APP_PASSWORD'],
            smtp_host=current_app.config['GMAIL_SMTP_HOST'],
            smtp_port=current_app.config['GMAIL_SMTP_PORT'],
            expiry_minutes=current_app.config['OTP_EXPIRY_SECONDS'] // 60,
        )

        user.last_login = utcnow()
        db.session.commit()

        return {'user_id': str(user.id), 'otp_required': True}, None

    @staticmethod
    def verify_otp(user_id: str, otp_input: str):
        entry = _otp_store.get(user_id)
        if not entry:
            return None, 'No pending OTP for this user'

        stored_otp, expires_at = entry
        if utcnow() > expires_at:
            _otp_store.pop(user_id, None)
            return None, 'OTP expired'
        if stored_otp != otp_input:
            return None, 'Invalid OTP'

        _otp_store.pop(user_id, None)
        user = db.session.get(User, uuid.UUID(user_id))
        if not user:
            return None, 'User not found'

        membership = user.memberships[0] if user.memberships else None
        additional_claims = {
            'role': membership.role if membership else 'user',
            'org_id': str(membership.organization_id) if membership else None,
            'is_super_admin': user.is_super_admin,
        }
        token = create_access_token(identity=user_id, additional_claims=additional_claims)
        return {'access_token': token, 'token_type': 'Bearer'}, None

    @staticmethod
    def hash_password(plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ── Telemetry + Firebase GPS Bridge ──────────────────────────────────────────

class TelemetryService:
    @staticmethod
    def ingest(device: Device, data: dict):
        """
        1. Persist Telemetry row.
        2. Update Vehicle denorm fields.
        3. Push GPS to Firebase RTDB.
        4. Run geofence + speed checks → create Alerts + send FCM.
        """
        vehicle = device.assigned_vehicle
        if not vehicle:
            return None, 'Device has no assigned vehicle'

        lat = float(data['latitude'])
        lng = float(data['longitude'])
        speed = float(data.get('speed', 0))

        # 1. Persist
        tel = Telemetry(
            vehicle_id=vehicle.id,
            device_id=device.id,
            latitude=lat,
            longitude=lng,
            altitude=data.get('altitude'),
            speed=speed,
            course=data.get('course', 0),
            engine_status=data.get('engine_status', True),
            odometer=data.get('odometer'),
            sensors=data.get('sensors', {}),
            timestamp=data.get('timestamp') or utcnow(),
            server_timestamp=utcnow(),
        )
        db.session.add(tel)
        db.session.flush()

        # 2. Denorm update
        vehicle.last_telemetry_id = tel.id
        vehicle.last_heartbeat = utcnow()
        vehicle.status = 'active'
        db.session.commit()

        # 3. Push to Firebase RTDB
        TelemetryService._push_firebase(vehicle, lat, lng, data.get('course', 0), speed)

        # 4. Event checks
        TelemetryService._check_geofences(vehicle, lat, lng)
        TelemetryService._check_speed(vehicle, speed)

        return {'telemetry_id': tel.id}, None

    @staticmethod
    def _push_firebase(vehicle: Vehicle, lat: float, lng: float, heading: int, speed: float):
        try:
            from firebase_admin import db as rtdb
            import time
            ref = rtdb.reference(f'/vehicles/{vehicle.id}')
            ref.update({
                'gps': {
                    'lat': lat,
                    'lng': lng,
                    'heading': int(heading),
                    'speed': int(speed),
                    'updatedAt': int(time.time() * 1000),
                },
                'meta': {
                    'plate': vehicle.license_plate,
                    'status': 'online',
                },
            })
        except Exception as exc:
            log.error('Firebase RTDB push failed: %s', exc)

    @staticmethod
    def _check_geofences(vehicle: Vehicle, lat: float, lng: float):
        geofences = Geofence.query.filter_by(
            organization_id=vehicle.organization_id,
            is_active=True,
        ).all()
        for fence in geofences:
            key = (str(vehicle.id), str(fence.id))
            inside = vehicle_in_geofence(lat, lng, {
                'fence_type': fence.fence_type,
                'geometry': fence.geometry,
            })
            was_inside = _geofence_state.get(key)
            _geofence_state[key] = inside

            # First reading for this vehicle/fence pair — just record state.
            if was_inside is None:
                continue
            # No boundary crossing — skip.
            if inside == was_inside:
                continue

            event = 'entered' if inside else 'exited'
            notify = (inside and fence.notify_on_enter) or (not inside and fence.notify_on_exit)
            if notify:
                AlertService.create(
                    organization_id=vehicle.organization_id,
                    vehicle=vehicle,
                    alert_type='geofence',
                    severity='medium',
                    message=f'{vehicle.license_plate} {event} zone "{fence.name}"',
                    extra_data={'zone': fence.name, 'event': event, 'fence_id': str(fence.id)},
                )

    @staticmethod
    def _check_speed(vehicle: Vehicle, speed: float):
        fence = Geofence.query.filter(
            Geofence.organization_id == vehicle.organization_id,
            Geofence.speed_limit.isnot(None),
            Geofence.is_active == True,
        ).first()
        if not fence or not fence.speed_limit:
            return

        vid = str(vehicle.id)
        was_over = _speed_alert_active.get(vid, False)
        is_over = speed > fence.speed_limit
        _speed_alert_active[vid] = is_over

        # Alert only when crossing into over-limit (not on every fast point).
        if is_over and not was_over:
            AlertService.create(
                organization_id=vehicle.organization_id,
                vehicle=vehicle,
                alert_type='speed',
                severity='high',
                message=f'{vehicle.license_plate} exceeded {fence.speed_limit} km/h (current: {int(speed)} km/h)',
                extra_data={'speed': speed, 'limit': fence.speed_limit},
            )


# ── Alert + FCM ───────────────────────────────────────────────────────────────

class AlertService:
    @staticmethod
    def create(organization_id, vehicle: Vehicle, alert_type: str,
               severity: str, message: str, extra_data: dict):
        alert = Alert(
            organization_id=organization_id,
            vehicle_id=vehicle.id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            extra_data=extra_data,
        )
        db.session.add(alert)
        db.session.commit()

        FCMService.notify_org(
            organization_id=organization_id,
            title=_alert_title(alert_type),
            body=message,
            data={
                'type': alert_type,
                'vehicleId': str(vehicle.id),
                'alertId': str(alert.id),
            },
        )
        return alert

    @staticmethod
    def resolve(alert_id: str, user_id: str):
        alert = db.session.get(Alert, uuid.UUID(alert_id))
        if not alert:
            return None, 'Alert not found'
        alert.resolved_at = utcnow()
        alert.resolved_by = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        db.session.commit()
        return alert, None


def _alert_title(alert_type: str) -> str:
    return {
        'geofence': 'Geofence Breach',
        'speed':    'Speed Limit Exceeded',
        'offline':  'Vehicle Signal Lost',
        'sos':      '🚨 SOS Alert',
    }.get(alert_type, 'Fleet Alert')


# ── FCM Token + Notification ──────────────────────────────────────────────────

class FCMService:
    @staticmethod
    def register_token(user_id: str, organization_id: str, fcm_token: str, platform: str):
        existing = DeviceFCMToken.query.filter_by(user_id=user_id, organization_id=organization_id).first()
        if existing:
            existing.fcm_token = fcm_token
            existing.platform = platform
        else:
            db.session.add(DeviceFCMToken(
                user_id=user_id,
                organization_id=organization_id,
                fcm_token=fcm_token,
                platform=platform,
            ))
        db.session.commit()

    @staticmethod
    def notify_org(organization_id, title: str, body: str, data: dict):
        """Send FCM push to all registered devices for an organisation."""
        tokens = [
            row.fcm_token
            for row in DeviceFCMToken.query.filter_by(organization_id=organization_id).all()
        ]
        if not tokens:
            return

        try:
            from firebase_admin import messaging
            channel = 'sos_alerts' if data.get('type') == 'sos' else 'fleet_alerts'
            response = messaging.send_each_for_multicast(
                messaging.MulticastMessage(
                    notification=messaging.Notification(title=title, body=body),
                    data={k: str(v) for k, v in data.items()},
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(channel_id=channel),
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(sound='default', badge=1),
                        ),
                    ),
                    tokens=tokens,
                )
            )
            if response.failure_count:
                log.warning('FCM: %d failures out of %d', response.failure_count, len(tokens))
        except Exception as exc:
            log.error('FCM send failed: %s', exc)
