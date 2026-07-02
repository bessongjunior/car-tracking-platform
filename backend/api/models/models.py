from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, Uuid
from sqlalchemy.ext.declarative import declared_attr
from datetime import datetime
import uuid

db = SQLAlchemy()


class TimestampMixin:
    @declared_attr
    def created_at(cls):
        return db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @declared_attr
    def updated_at(cls):
        return db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Organization(db.Model, TimestampMixin):
    __tablename__ = 'organizations'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    settings = db.Column(JSON, default={})
    is_active = db.Column(db.Boolean, default=True)

    members = db.relationship('OrganizationMember', back_populates='organization', cascade='all, delete-orphan')
    vehicles = db.relationship('Vehicle', backref='organization', lazy='dynamic')
    devices = db.relationship('Device', backref='organization', lazy='dynamic')
    geofences = db.relationship('Geofence', backref='organization', lazy='dynamic')
    alerts = db.relationship('Alert', backref='organization', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='organization', lazy='dynamic')
    fcm_tokens = db.relationship('DeviceFCMToken', backref='organization', lazy='dynamic')


class User(db.Model, TimestampMixin):
    __tablename__ = 'users'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100))
    is_super_admin = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    memberships = db.relationship('OrganizationMember', back_populates='user', cascade='all, delete-orphan')
    actions_performed = db.relationship('AuditLog', backref='performer', lazy='dynamic')
    fcm_tokens = db.relationship('DeviceFCMToken', back_populates='user', cascade='all, delete-orphan')


class OrganizationMember(db.Model, TimestampMixin):
    __tablename__ = 'organization_members'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)

    user = db.relationship('User', back_populates='memberships')
    organization = db.relationship('Organization', back_populates='members')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'organization_id', name='_user_org_uc'),
    )


class Vehicle(db.Model, TimestampMixin):
    __tablename__ = 'vehicles'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    license_plate = db.Column(db.String(20), unique=True, nullable=False)
    vin = db.Column(db.String(17), unique=True)
    vehicle_type = db.Column(db.String(30))
    extra_data = db.Column(JSON, default={})
    current_device_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('devices.id'))
    last_telemetry_id = db.Column(db.BigInteger)
    last_heartbeat = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')


class Device(db.Model, TimestampMixin):
    __tablename__ = 'devices'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    serial_number = db.Column(db.String(50), unique=True, nullable=False)
    imei = db.Column(db.String(20), unique=True)
    device_model = db.Column(db.String(50))
    firmware_version = db.Column(db.String(20))
    api_key = db.Column(db.String(64), unique=True, nullable=False, default=lambda: uuid.uuid4().hex)
    status = db.Column(db.String(20), default='offline')

    assigned_vehicle = db.relationship(
        'Vehicle',
        foreign_keys=[Vehicle.current_device_id],
        backref='device',
        uselist=False,
    )


class Telemetry(db.Model):
    __tablename__ = 'telemetry'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    vehicle_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('vehicles.id'), nullable=False, index=True)
    device_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('devices.id'), nullable=False)
    latitude = db.Column(db.Numeric(precision=9, scale=6), nullable=False)
    longitude = db.Column(db.Numeric(precision=9, scale=6), nullable=False)
    altitude = db.Column(db.Float)
    speed = db.Column(db.Float)
    course = db.Column(db.Integer)
    engine_status = db.Column(db.Boolean)
    odometer = db.Column(db.Numeric(precision=12, scale=2))
    sensors = db.Column(JSON, default={})
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    server_timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Geofence(db.Model, TimestampMixin):
    __tablename__ = 'geofences'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    fence_type = db.Column(db.String(20))  # 'polygon' | 'circle'
    geometry = db.Column(JSON, nullable=False)
    speed_limit = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    notify_on_enter = db.Column(db.Boolean, default=True)
    notify_on_exit = db.Column(db.Boolean, default=True)


class Alert(db.Model, TimestampMixin):
    __tablename__ = 'alerts'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    vehicle_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('vehicles.id'), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)  # geofence | speed | offline | sos
    severity = db.Column(db.String(20), default='medium')  # low | medium | high | critical
    message = db.Column(db.Text)
    extra_data = db.Column(JSON)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(Uuid(as_uuid=True), db.ForeignKey('users.id'))

    vehicle = db.relationship('Vehicle', backref='alerts')


class DeviceFCMToken(db.Model, TimestampMixin):
    """Stores FCM tokens for push notification delivery to fleet managers."""
    __tablename__ = 'device_fcm_tokens'

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    fcm_token = db.Column(db.Text, unique=True, nullable=False)
    platform = db.Column(db.String(10))  # android | ios

    user = db.relationship('User', back_populates='fcm_tokens')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'organization_id', name='_user_org_fcm_uc'),
    )


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    organization_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('organizations.id'), nullable=True)
    user_id = db.Column(Uuid(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.String(36), nullable=True)
    changes = db.Column(JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
