import os
from dotenv import load_dotenv

load_dotenv()

_db_url = os.environ.get('DATABASE_URL', 'sqlite:///cartracker.db')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SQLite requires check_same_thread=False when using gthread workers.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        **(
            {'connect_args': {'check_same_thread': False}}
            if _db_url.startswith('sqlite')
            else {}
        ),
    }

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-change-me-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 3600))  # 1 hour

    FIREBASE_DATABASE_URL = os.environ.get('FIREBASE_DATABASE_URL', '')
    FIREBASE_CREDENTIALS = os.environ.get('FIREBASE_CREDENTIALS', 'serviceAccountKey.json')

    # OTP config
    OTP_EXPIRY_SECONDS = int(os.environ.get('OTP_EXPIRY_SECONDS', 300))  # 5 min

    # SMTP (supports SMTP_* or legacy GMAIL_* variable names)
    GMAIL_SENDER       = os.environ.get('SMTP_USERNAME',   os.environ.get('GMAIL_SENDER',       'noreply@yourdomain.com'))
    GMAIL_APP_PASSWORD = os.environ.get('SMTP_PASSWORD',   os.environ.get('GMAIL_APP_PASSWORD', ''))
    GMAIL_SMTP_HOST    = os.environ.get('SMTP_ADDRESS',    os.environ.get('GMAIL_SMTP_HOST',    'smtp.gmail.com'))
    GMAIL_SMTP_PORT    = int(os.environ.get('SMTP_PORT',   os.environ.get('GMAIL_SMTP_PORT',    587)))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
