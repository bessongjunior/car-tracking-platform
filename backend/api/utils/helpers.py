import random
import string
from datetime import datetime, timezone
from functools import wraps

from flask import request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from ..utils.custom_response import error


def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def require_role(*roles):
    """Decorator: ensure the JWT bearer has one of the given org roles."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get('role') not in roles and not claims.get('is_super_admin'):
                return error('Insufficient permissions', 403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_device_from_request():
    """Resolve a Device from the X-Device-Key header."""
    from ..models.models import Device
    api_key = request.headers.get('X-Device-Key')
    if not api_key:
        return None, error('Missing X-Device-Key header', 401)
    device = Device.query.filter_by(api_key=api_key).first()
    if not device:
        return None, error('Invalid device key', 401)
    return device, None
