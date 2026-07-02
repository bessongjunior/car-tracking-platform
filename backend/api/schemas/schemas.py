from marshmallow import Schema, fields, validate


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True)


class OtpVerifySchema(Schema):
    user_id = fields.String(required=True)
    otp = fields.String(required=True, validate=validate.Length(equal=6))


class TelemetryIngestSchema(Schema):
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    speed = fields.Float(load_default=0.0)
    course = fields.Integer(load_default=0)
    altitude = fields.Float(load_default=None)
    engine_status = fields.Boolean(load_default=True)
    odometer = fields.Float(load_default=None)
    sensors = fields.Dict(load_default={})
    timestamp = fields.DateTime(load_default=None)


class FCMTokenSchema(Schema):
    fcm_token = fields.String(required=True)
    platform = fields.String(
        required=True,
        validate=validate.OneOf(['android', 'ios']),
    )


class GeofenceCreateSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    fence_type = fields.String(
        required=True,
        validate=validate.OneOf(['polygon', 'circle']),
    )
    geometry = fields.Dict(required=True)
    speed_limit = fields.Integer(load_default=None)
    notify_on_enter = fields.Boolean(load_default=True)
    notify_on_exit = fields.Boolean(load_default=True)


class VehicleSchema(Schema):
    id = fields.String()
    name = fields.String()
    license_plate = fields.String()
    vin = fields.String()
    vehicle_type = fields.String()
    status = fields.String()
    last_heartbeat = fields.DateTime()


class AlertSchema(Schema):
    id = fields.String()
    vehicle_id = fields.String()
    alert_type = fields.String()
    severity = fields.String()
    message = fields.String()
    extra_data = fields.Dict()
    created_at = fields.DateTime()
    resolved_at = fields.DateTime()
