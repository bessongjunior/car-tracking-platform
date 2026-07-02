import math

from flask import Blueprint, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from marshmallow import ValidationError

from ..models.models import Alert, Geofence, Telemetry, User, Vehicle, db
from ..schemas.schemas import (
    FCMTokenSchema, GeofenceCreateSchema, LoginSchema,
    OtpVerifySchema, TelemetryIngestSchema,
)
from ..services.services import AlertService, AuthService, FCMService, TelemetryService
from ..utils.custom_response import error, success
from ..utils.helpers import get_device_from_request, require_role

api_bp = Blueprint('api', __name__)


# ── Auth ──────────────────────────────────────────────────────────────────────

@api_bp.post('/auth/login')
def login():
    """
    Initiate login — sends OTP to the user's registered email.
    ---
    tags:
      - Auth
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [email, password]
            properties:
              email:
                type: string
                format: email
                example: manager@tieftechnologiesltd.com
              password:
                type: string
                format: password
                example: "Str0ngP@ssword!"
    responses:
      200:
        description: OTP dispatched to the user's email address.
        content:
          application/json:
            schema:
              type: object
              properties:
                status:  {type: string, example: success}
                message: {type: string, example: OTP sent to registered device}
                data:
                  type: object
                  properties:
                    user_id:      {type: string, example: "42"}
                    otp_required: {type: boolean, example: true}
      401:
        description: Invalid credentials.
      422:
        description: Validation error (missing fields).
    """
    try:
        data = LoginSchema().load(request.get_json() or {})
    except ValidationError as e:
        return error('Validation failed', 422, e.messages)

    result, err = AuthService.login(data['email'], data['password'])
    if err:
        return error(err, 401)
    return success(result, 'OTP sent to registered device')


@api_bp.post('/auth/verify-otp')
def verify_otp():
    """
    Verify the 6-digit OTP and receive a JWT access token.
    ---
    tags:
      - Auth
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [user_id, otp]
            properties:
              user_id:
                type: string
                example: "42"
              otp:
                type: string
                minLength: 6
                maxLength: 6
                example: "839201"
    responses:
      200:
        description: "Authentication successful. Pass the token as 'Authorization: Bearer <token>'."
        content:
          application/json:
            schema:
              type: object
              properties:
                status:  {type: string, example: success}
                message: {type: string, example: Authenticated}
                data:
                  type: object
                  properties:
                    access_token: {type: string, example: eyJhbGci...}
                    token_type:   {type: string, example: Bearer}
      401:
        description: Invalid or expired OTP.
    """
    try:
        data = OtpVerifySchema().load(request.get_json() or {})
    except ValidationError as e:
        return error('Validation failed', 422, e.messages)

    result, err = AuthService.verify_otp(data['user_id'], data['otp'])
    if err:
        return error(err, 401)
    return success(result, 'Authenticated')


# ── Vehicles ──────────────────────────────────────────────────────────────────

@api_bp.get('/vehicles')
@jwt_required()
def list_vehicles():
    """
    List all vehicles belonging to the authenticated user's organisation.
    ---
    tags:
      - Vehicles
    security:
      - BearerAuth: []
    responses:
      200:
        description: Array of vehicle objects.
        content:
          application/json:
            schema:
              type: object
              properties:
                status: {type: string, example: success}
                data:
                  type: array
                  items:
                    type: object
                    properties:
                      id:             {type: string, example: "7"}
                      name:           {type: string, example: Hilux-01}
                      license_plate:  {type: string, example: GE-1234-21}
                      vin:            {type: string, example: 1HGBH41JXMN109186}
                      vehicle_type:   {type: string, example: pickup}
                      status:         {type: string, example: online}
                      last_heartbeat: {type: string, format: date-time}
      401:
        description: Missing or invalid JWT.
    """
    claims = get_jwt()
    org_id = claims.get('org_id')
    vehicles = Vehicle.query.filter_by(organization_id=org_id).all()
    data = [
        {
            'id': str(v.id),
            'name': v.name,
            'license_plate': v.license_plate,
            'vin': v.vin,
            'vehicle_type': v.vehicle_type,
            'status': v.status,
            'last_heartbeat': v.last_heartbeat.isoformat() if v.last_heartbeat else None,
        }
        for v in vehicles
    ]
    return success(data)


@api_bp.get('/vehicles/<vehicle_id>')
@jwt_required()
def get_vehicle(vehicle_id):
    """
    Retrieve a single vehicle by ID.
    ---
    tags:
      - Vehicles
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: vehicle_id
        required: true
        schema: {type: string}
        example: "7"
    responses:
      200:
        description: Vehicle detail including extra_data.
      401:
        description: Missing or invalid JWT.
      404:
        description: Vehicle not found or does not belong to this organisation.
    """
    claims = get_jwt()
    org_id = claims.get('org_id')
    vehicle = Vehicle.query.filter_by(id=vehicle_id, organization_id=org_id).first()
    if not vehicle:
        return error('Vehicle not found', 404)
    return success({
        'id': str(vehicle.id),
        'name': vehicle.name,
        'license_plate': vehicle.license_plate,
        'vin': vehicle.vin,
        'vehicle_type': vehicle.vehicle_type,
        'status': vehicle.status,
        'last_heartbeat': vehicle.last_heartbeat.isoformat() if vehicle.last_heartbeat else None,
        'extra_data': vehicle.extra_data,
    })


# ── Telemetry (GPS device → backend → Firebase) ───────────────────────────────

@api_bp.post('/telemetry')
def ingest_telemetry():
    """
    Ingest a GPS telemetry point from a hardware tracking device.
    Auth: X-Device-Key header (not JWT).
    ---
    tags:
      - Telemetry
    parameters:
      - in: header
        name: X-Device-Key
        required: true
        schema: {type: string}
        description: API key assigned to the physical GPS device.
        example: dev-abc-123
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [latitude, longitude]
            properties:
              latitude:      {type: number, format: float, example: 5.6037}
              longitude:     {type: number, format: float, example: -0.1870}
              speed:         {type: number, format: float, example: 64.5}
              course:        {type: integer, example: 90}
              altitude:      {type: number, format: float, example: 61.0}
              engine_status: {type: boolean, example: true}
              odometer:      {type: number, format: float, example: 24309.7}
              sensors:       {type: object, example: {fuel_level: 82}}
              timestamp:     {type: string, format: date-time}
    responses:
      201:
        description: Telemetry recorded, Firebase RTDB updated, geofence checks run.
      400:
        description: Validation error or device has no assigned vehicle.
      401:
        description: Missing or invalid X-Device-Key header.
    """
    device, err_response = get_device_from_request()
    if err_response:
        return err_response

    try:
        data = TelemetryIngestSchema().load(request.get_json() or {})
    except ValidationError as e:
        return error('Validation failed', 422, e.messages)

    result, err = TelemetryService.ingest(device, data)
    if err:
        return error(err, 400)
    return success(result, 'Telemetry recorded', 201)


# ── FCM Token Registration ────────────────────────────────────────────────────

@api_bp.post('/devices/fcm-token')
@jwt_required()
def register_fcm_token():
    """
    Register or update the FCM push-notification token for the current user's device.
    ---
    tags:
      - Devices
    security:
      - BearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [fcm_token, platform]
            properties:
              fcm_token:
                type: string
                example: "fxyz123...ABCdefTokenFromFirebase"
              platform:
                type: string
                enum: [android, ios]
                example: android
    responses:
      200:
        description: FCM token saved or updated.
      401:
        description: Missing or invalid JWT.
      422:
        description: Validation error.
    """
    try:
        data = FCMTokenSchema().load(request.get_json() or {})
    except ValidationError as e:
        return error('Validation failed', 422, e.messages)

    claims = get_jwt()
    user_id = get_jwt_identity()
    org_id = claims.get('org_id')

    FCMService.register_token(user_id, org_id, data['fcm_token'], data['platform'])
    return success(message='FCM token registered')


# ── Alerts ────────────────────────────────────────────────────────────────────

@api_bp.get('/alerts')
@jwt_required()
def list_alerts():
    """
    List fleet alerts for the authenticated user's organisation.
    ---
    tags:
      - Alerts
    security:
      - BearerAuth: []
    parameters:
      - in: query
        name: resolved
        schema: {type: boolean, default: false}
        description: Set to true to include already-resolved alerts.
    responses:
      200:
        description: Array of alert objects ordered newest-first (max 100).
        content:
          application/json:
            schema:
              type: object
              properties:
                status: {type: string, example: success}
                data:
                  type: array
                  items:
                    type: object
                    properties:
                      id:            {type: string}
                      vehicle_id:    {type: string}
                      vehicle_plate: {type: string, example: GE-1234-21}
                      alert_type:    {type: string, enum: [geofence, speed, sos, offline]}
                      severity:      {type: string, enum: [low, medium, high, critical]}
                      message:       {type: string}
                      created_at:    {type: string, format: date-time}
                      resolved_at:   {type: string, format: date-time, nullable: true}
      401:
        description: Missing or invalid JWT.
    """
    claims = get_jwt()
    org_id = claims.get('org_id')
    resolved = request.args.get('resolved', 'false').lower() == 'true'

    query = Alert.query.filter_by(organization_id=org_id)
    if not resolved:
        query = query.filter(Alert.resolved_at.is_(None))

    alerts = query.order_by(Alert.created_at.desc()).limit(100).all()
    data = [
        {
            'id': str(a.id),
            'vehicle_id': str(a.vehicle_id),
            'vehicle_plate': a.vehicle.license_plate if a.vehicle else None,
            'alert_type': a.alert_type,
            'severity': a.severity,
            'message': a.message,
            'extra_data': a.extra_data,
            'created_at': a.created_at.isoformat(),
            'resolved_at': a.resolved_at.isoformat() if a.resolved_at else None,
        }
        for a in alerts
    ]
    return success(data)


@api_bp.patch('/alerts/<alert_id>/resolve')
@jwt_required()
def resolve_alert(alert_id):
    """
    Mark an alert as resolved.
    ---
    tags:
      - Alerts
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: alert_id
        required: true
        schema: {type: string}
        example: "15"
    responses:
      200:
        description: Alert resolved — returns the resolved timestamp.
      401:
        description: Missing or invalid JWT.
      404:
        description: Alert not found.
    """
    user_id = get_jwt_identity()
    alert, err = AlertService.resolve(alert_id, user_id)
    if err:
        return error(err, 404)
    return success({'id': str(alert.id), 'resolved_at': alert.resolved_at.isoformat()})


# ── Geofences ─────────────────────────────────────────────────────────────────

@api_bp.get('/geofences')
@jwt_required()
def list_geofences():
    """
    List active geofence zones for the organisation.
    ---
    tags:
      - Geofences
    security:
      - BearerAuth: []
    responses:
      200:
        description: Array of active geofence objects.
        content:
          application/json:
            schema:
              type: object
              properties:
                status: {type: string, example: success}
                data:
                  type: array
                  items:
                    type: object
                    properties:
                      id:              {type: string}
                      name:            {type: string, example: Accra Central}
                      fence_type:      {type: string, enum: [circle, polygon]}
                      geometry:        {type: object}
                      speed_limit:     {type: integer, nullable: true, example: 80}
                      notify_on_enter: {type: boolean}
                      notify_on_exit:  {type: boolean}
                      created_at:      {type: string, format: date-time}
      401:
        description: Missing or invalid JWT.
    """
    claims = get_jwt()
    org_id = claims.get('org_id')
    fences = Geofence.query.filter_by(organization_id=org_id, is_active=True).all()
    data = [
        {
            'id': str(f.id),
            'name': f.name,
            'fence_type': f.fence_type,
            'geometry': f.geometry,
            'speed_limit': f.speed_limit,
            'notify_on_enter': f.notify_on_enter,
            'notify_on_exit': f.notify_on_exit,
            'created_at': f.created_at.isoformat(),
        }
        for f in fences
    ]
    return success(data)


@api_bp.post('/geofences')
@jwt_required()
@require_role('admin')
def create_geofence():
    """
    Create a new geofence zone. Requires the `admin` role.
    ---
    tags:
      - Geofences
    security:
      - BearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required: [name, fence_type, geometry]
            properties:
              name:
                type: string
                example: Tema Port Zone
              fence_type:
                type: string
                enum: [circle, polygon]
                example: circle
              geometry:
                type: object
                example:
                  center: {lat: 5.6037, lng: -0.1870}
                  radius: 500
              speed_limit:
                type: integer
                nullable: true
                example: 80
              notify_on_enter:
                type: boolean
                default: true
              notify_on_exit:
                type: boolean
                default: true
    responses:
      201:
        description: Geofence created.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient role — admin required.
      422:
        description: Validation error.
    """
    try:
        data = GeofenceCreateSchema().load(request.get_json() or {})
    except ValidationError as e:
        return error('Validation failed', 422, e.messages)

    claims = get_jwt()
    org_id = claims.get('org_id')

    fence = Geofence(
        organization_id=org_id,
        name=data['name'],
        fence_type=data['fence_type'],
        geometry=data['geometry'],
        speed_limit=data.get('speed_limit'),
        notify_on_enter=data.get('notify_on_enter', True),
        notify_on_exit=data.get('notify_on_exit', True),
    )
    db.session.add(fence)
    db.session.commit()
    return success({'id': str(fence.id), 'name': fence.name}, 'Geofence created', 201)


@api_bp.delete('/geofences/<fence_id>')
@jwt_required()
@require_role('admin')
def delete_geofence(fence_id):
    """
    Soft-delete a geofence zone (sets is_active = false). Requires `admin` role.
    ---
    tags:
      - Geofences
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: fence_id
        required: true
        schema: {type: string}
        example: "3"
    responses:
      200:
        description: Geofence deactivated.
      401:
        description: Missing or invalid JWT.
      403:
        description: Insufficient role.
      404:
        description: Geofence not found.
    """
    claims = get_jwt()
    org_id = claims.get('org_id')
    fence = Geofence.query.filter_by(id=fence_id, organization_id=org_id).first()
    if not fence:
        return error('Geofence not found', 404)
    fence.is_active = False
    db.session.commit()
    return success(message='Geofence deleted')


# ── Firebase Sample Endpoints ─────────────────────────────────────────────────

@api_bp.post('/firebase/gps/seed')
def firebase_seed_gps():
    """
    Push a mock GPS point to Firebase RTDB for a vehicle (dev/test only).
    ---
    tags:
      - Firebase
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              vehicle_id: {type: string, example: hilux-01}
              lat:        {type: number, example: 5.6037}
              lng:        {type: number, example: -0.1870}
              heading:    {type: integer, example: 90}
              speed:      {type: integer, example: 64}
              plate:      {type: string, example: GE-1234-21}
    responses:
      201:
        description: GPS data written to Firebase RTDB.
      503:
        description: Firebase not initialised or unreachable.
    """
    data = request.get_json() or {}
    vehicle_id = data.get('vehicle_id', 'demo-vehicle-01')
    lat = float(data.get('lat', 5.6037))
    lng = float(data.get('lng', -0.1870))
    heading = int(data.get('heading', 0))
    speed = int(data.get('speed', 0))

    try:
        import time
        from firebase_admin import db as rtdb
        ref = rtdb.reference(f'/vehicles/{vehicle_id}')
        payload = {
            'gps': {
                'lat': lat,
                'lng': lng,
                'heading': heading,
                'speed': speed,
                'updatedAt': int(time.time() * 1000),
            },
            'meta': {
                'plate': data.get('plate', 'DEMO-001'),
                'status': 'online',
            },
        }
        ref.set(payload)
        return success({
            'vehicle_id': vehicle_id,
            'written': payload,
            'path': f'/vehicles/{vehicle_id}',
        }, 'GPS seeded to Firebase RTDB', 201)
    except Exception as exc:
        return error(f'Firebase write failed: {exc}', 503)


@api_bp.get('/firebase/gps/<vehicle_id>')
def firebase_read_gps(vehicle_id):
    """
    Read the current GPS snapshot for a vehicle from Firebase RTDB (dev/test only).
    ---
    tags:
      - Firebase
    parameters:
      - in: path
        name: vehicle_id
        required: true
        schema: {type: string}
        example: hilux-01
    responses:
      200:
        description: Current GPS snapshot from Firebase RTDB.
      404:
        description: No GPS data found for this vehicle ID.
      503:
        description: Firebase not initialised or unreachable.
    """
    try:
        from firebase_admin import db as rtdb
        ref = rtdb.reference(f'/vehicles/{vehicle_id}/gps')
        snapshot = ref.get()
        if snapshot is None:
            return error(f'No GPS data found for vehicle {vehicle_id}', 404)
        return success({'vehicle_id': vehicle_id, 'gps': snapshot})
    except Exception as exc:
        return error(f'Firebase read failed: {exc}', 503)


@api_bp.get('/firebase/status')
def firebase_status():
    """
    Check whether the Firebase Admin SDK is initialised and the RTDB is reachable.
    ---
    tags:
      - Firebase
    responses:
      200:
        description: Firebase connectivity status.
      503:
        description: Firebase unreachable or SDK not initialised.
    """
    try:
        import firebase_admin
        from firebase_admin import db as rtdb
        if not firebase_admin._apps:
            return success({'firebase': 'not_initialised',
                            'hint': 'Set FIREBASE_CREDENTIALS and FIREBASE_DATABASE_URL in .env'})
        rtdb.reference('/').get()
        return success({'firebase': 'connected',
                        'database_url': rtdb.reference('/').path})
    except Exception as exc:
        return error(f'Firebase unreachable: {exc}', 503)


# ── Users ─────────────────────────────────────────────────────────────────────

@api_bp.get('/users/me')
@jwt_required()
def get_me():
    """
    Return the authenticated user's profile and organisation info.
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    responses:
      200:
        description: User profile object.
      401:
        description: Missing or invalid JWT.
      404:
        description: User not found.
    """
    user_id = get_jwt_identity()
    claims  = get_jwt()

    user = db.session.get(User, user_id)
    if not user:
        return error('User not found', 404)

    membership = user.memberships[0] if user.memberships else None
    org = membership.organization if membership else None

    return success({
        'id':            str(user.id),
        'full_name':     user.full_name or '',
        'email':         user.email,
        'role':          claims.get('role', 'user'),
        'organization':  org.name if org else '',
        'organization_id': str(org.id) if org else None,
        'is_super_admin': user.is_super_admin,
        'last_login':    user.last_login.isoformat() if user.last_login else None,
    })


# ── Telemetry History ─────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two GPS points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@api_bp.get('/telemetry/history')
@jwt_required()
def telemetry_history():
    """
    Return recent trips aggregated from telemetry, grouped per vehicle.
    A gap of more than 30 minutes between consecutive points marks a new trip.
    ---
    tags:
      - Telemetry
    security:
      - BearerAuth: []
    parameters:
      - in: query
        name: limit
        schema: {type: integer, default: 20}
        description: Maximum number of trips to return.
    responses:
      200:
        description: Array of trip summaries ordered newest-first.
      401:
        description: Missing or invalid JWT.
    """
    claims = get_jwt()
    org_id = claims.get('org_id')
    limit  = min(int(request.args.get('limit', 20)), 100)

    vehicles = Vehicle.query.filter_by(organization_id=org_id).all()
    trips = []

    for vehicle in vehicles:
        rows = (
            Telemetry.query
            .filter_by(vehicle_id=vehicle.id)
            .order_by(Telemetry.timestamp.asc())
            .limit(200)
            .all()
        )
        if not rows:
            continue

        # Split into trip segments (gap > 30 min = new trip)
        groups = []
        current = [rows[0]]
        for row in rows[1:]:
            gap = (row.timestamp - current[-1].timestamp).total_seconds()
            if gap > 1800:
                groups.append(current)
                current = [row]
            else:
                current.append(row)
        groups.append(current)

        for group in groups:
            if len(group) < 2:
                continue

            dist = sum(
                _haversine_km(
                    float(group[i].latitude),   float(group[i].longitude),
                    float(group[i+1].latitude), float(group[i+1].longitude),
                )
                for i in range(len(group) - 1)
            )

            duration_min = max(
                1,
                int((group[-1].timestamp - group[0].timestamp).total_seconds() / 60),
            )
            speeds    = [float(r.speed or 0) for r in group]
            avg_speed = int(sum(speeds) / len(speeds))
            max_speed = int(max(speeds))

            trips.append({
                'trip_date':      group[0].timestamp.date().isoformat(),
                'vehicle_id':     str(vehicle.id),
                'vehicle_name':   vehicle.name,
                'license_plate':  vehicle.license_plate,
                'distance_km':    round(dist, 2),
                'duration_minutes': duration_min,
                'avg_speed_kmh':  avg_speed,
                'max_speed_kmh':  max_speed,
                'point_count':    len(group),
                'start_time':     group[0].timestamp.isoformat(),
                'end_time':       group[-1].timestamp.isoformat(),
            })

    trips.sort(key=lambda t: t['start_time'], reverse=True)
    return success(trips[:limit])


# ── Health ────────────────────────────────────────────────────────────────────

@api_bp.get('/health')
def health():
    """
    Health check — returns 200 if the API process is running.
    ---
    tags:
      - Health
    responses:
      200:
        description: API is up.
        content:
          application/json:
            schema:
              type: object
              properties:
                status: {type: string, example: success}
                data:
                  type: object
                  properties:
                    status: {type: string, example: ok}
    """
    return success({'status': 'ok'})
