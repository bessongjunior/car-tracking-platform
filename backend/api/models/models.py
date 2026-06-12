from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    """
    Multi-tenancy support. Everything belongs to an Organization.
    """
    __tablename__ = 'organizations'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    settings = db.Column(JSONB, default={})
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    members = db.relationship('OrganizationMember', back_populates='organization', cascade='all, delete-orphan')
    vehicles = db.relationship('Vehicle', backref='organization', lazy='dynamic')
    devices = db.relationship('Device', backref='organization', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='organization', lazy='dynamic')

class User(db.Model, TimestampMixin):
    """
    Global User Entity.
    """
    __tablename__ = 'users'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100))
    
    # Global flag for Super Admin (cross-organization access)
    is_super_admin = db.Column(db.Boolean, default=False)
    
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    memberships = db.relationship('OrganizationMember', back_populates='user', cascade='all, delete-orphan')
    actions_performed = db.relationship('AuditLog', backref='performer', lazy='dynamic')

class OrganizationMember(db.Model, TimestampMixin):
    """
    Association table linking Users to Organizations with specific roles.
    Allows a user to belong to multiple organizations.
    """
    __tablename__ = 'organization_members'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    
    # Role within this specific organization: 'admin' or 'user'
    role = db.Column(db.String(20), default='user', nullable=False)
    
    # Relationships
    user = db.relationship('User', back_populates='memberships')
    organization = db.relationship('Organization', back_populates='members')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'organization_id', name='_user_org_uc'),
    )

class Vehicle(db.Model, TimestampMixin):
    __tablename__ = 'vehicles'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    
    name = db.Column(db.String(50), nullable=False)
    license_plate = db.Column(db.String(20), unique=True, nullable=False)
    vin = db.Column(db.String(17), unique=True)
    
    vehicle_type = db.Column(db.String(30))
    metadata = db.Column(JSONB, default={})
    
    current_device_id = db.Column(UUID(as_uuid=True), db.ForeignKey('devices.id'))
    last_telemetry_id = db.Column(db.BigInteger)
    last_heartbeat = db.Column(db.DateTime)
    
    status = db.Column(db.String(20), default='active')

class Device(db.Model, TimestampMixin):
    __tablename__ = 'devices'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    
    serial_number = db.Column(db.String(50), unique=True, nullable=False)
    imei = db.Column(db.String(20), unique=True)
    device_model = db.Column(db.String(50))
    firmware_version = db.Column(db.String(20))
    
    status = db.Column(db.String(20), default='offline')
    
    assigned_vehicle = db.relationship('Vehicle', foreign_keys=[Vehicle.current_device_id], backref='device', uselist=False)

class Telemetry(db.Model):
    __tablename__ = 'telemetry'
    
    id = db.Column(db.BigInteger, primary_key=True)
    vehicle_id = db.Column(UUID(as_uuid=True), db.ForeignKey('vehicles.id'), nullable=False, index=True)
    device_id = db.Column(UUID(as_uuid=True), db.ForeignKey('devices.id'), nullable=False)
    
    latitude = db.Column(db.Numeric(precision=9, scale=6), nullable=False)
    longitude = db.Column(db.Numeric(precision=9, scale=6), nullable=False)
    altitude = db.Column(db.Float)
    speed = db.Column(db.Float)
    course = db.Column(db.Integer)
    
    engine_status = db.Column(db.Boolean)
    odometer = db.Column(db.Numeric(precision=12, scale=2))
    sensors = db.Column(JSONB, default={}) 
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    server_timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class Geofence(db.Model, TimestampMixin):
    __tablename__ = 'geofences'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)
    fence_type = db.Column(db.String(20))
    geometry = db.Column(JSONB, nullable=False) 
    is_active = db.Column(db.Boolean, default=True)

class Alert(db.Model, TimestampMixin):
    __tablename__ = 'alerts'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organizations.id'), nullable=False)
    vehicle_id = db.Column(UUID(as_uuid=True), db.ForeignKey('vehicles.id'), nullable=False)
    
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default='medium')
    message = db.Column(db.Text)
    metadata = db.Column(JSONB)
    
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))

class AuditLog(db.Model):
    """
    Comprehensive audit trail for security and compliance.
    Tracks 'Who did What, to Whom, When, and from Where'.
    """
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey('organizations.id'), nullable=True) # Null for global/system actions
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True) # Null for system/hardware actions
    
    # Activity Details
    action = db.Column(db.String(50), nullable=False, index=True) # e.g., 'create', 'update', 'delete', 'login'
    target_type = db.Column(db.String(50), nullable=False) # e.g., 'Vehicle', 'User', 'Geofence'
    target_id = db.Column(db.String(36), nullable=True) # The ID of the affected resource
    
    # State Changes
    changes = db.Column(JSONB) # e.g., {"old": {"status": "active"}, "new": {"status": "maintenance"}}
    
    # Context
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<AuditLog {self.action} on {self.target_type} by {self.user_id}>'
