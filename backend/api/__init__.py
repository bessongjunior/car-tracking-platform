import logging
import os

import firebase_admin
from flasgger import Swagger
from firebase_admin import credentials
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from .configs.configs import config_map
from .models.models import db
from .routes.routes import api_bp

log = logging.getLogger(__name__)

# ── Swagger / flasgger config ─────────────────────────────────────────────────

SWAGGER_CONFIG = {
    'title': 'CarTracker Fleet API',
    'uiversion': 3,
    'openapi': '3.0.3',
    'specs': [
        {
            'endpoint': 'apispec',
            'route': '/api/v1/apispec.json',
            'rule_filter': lambda rule: True,
            'model_filter': lambda tag: True,
        }
    ],
    'static_url_path': '/flasgger_static',
    'swagger_ui': True,
    'specs_route': '/api/v1/docs/',
    'headers': [],
}

SWAGGER_TEMPLATE = {
    'info': {
        'title': 'CarTracker Fleet API',
        'description': (
            'REST API for the CarTracker fleet intelligence platform by '
            'Tief Technologies Ltd. All protected endpoints require a '
            'Bearer JWT obtained via `POST /api/v1/auth/verify-otp`.'
        ),
        'version': '1.0.0',
        'contact': {
            'name': 'Tief Technologies Ltd',
            'email': 'dev@tieftechnologiesltd.com',
        },
    },
    'servers': [
        {'url': '/api/v1', 'description': 'Current server'},
    ],
    'components': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
    'security': [{'BearerAuth': []}],
    'tags': [
        {'name': 'Auth',      'description': 'Login, OTP verification'},
        {'name': 'Vehicles',  'description': 'Fleet vehicle management'},
        {'name': 'Telemetry', 'description': 'GPS ingest from hardware devices'},
        {'name': 'Alerts',    'description': 'Fleet event alerts'},
        {'name': 'Geofences', 'description': 'Geofence zone management'},
        {'name': 'Devices',   'description': 'FCM push-notification tokens'},
        {'name': 'Firebase',  'description': 'Firebase RTDB helpers (dev/test)'},
        {'name': 'Health',    'description': 'Health check'},
    ],
}


# ── Firebase init ─────────────────────────────────────────────────────────────

def _init_firebase(app: Flask):
    cred_path = app.config['FIREBASE_CREDENTIALS']
    db_url = app.config['FIREBASE_DATABASE_URL']

    if not db_url:
        log.warning('FIREBASE_DATABASE_URL not set — Firebase disabled')
        return
    if not os.path.exists(cred_path):
        log.warning('Firebase credentials file not found at %s — Firebase disabled', cred_path)
        return

    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {'databaseURL': db_url})
        log.info('Firebase Admin SDK initialised')


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(env: str = 'default') -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_map[env])

    CORS(app)
    JWTManager(app)
    db.init_app(app)

    with app.app_context():
        try:
            db.create_all()
        except Exception as exc:
            log.error('DB init skipped — check DATABASE_URL: %s', exc)
        _init_firebase(app)

    app.register_blueprint(api_bp, url_prefix='/api/v1')

    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)

    logging.basicConfig(level=logging.INFO)
    return app
