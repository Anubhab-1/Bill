import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration shared across all environments."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    # Sessions expire after 8 hours (one work shift)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Feature Flags (Default)
    CLOUD_DEMO = False
    LOCAL_PRODUCTION = False

class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{os.path.join(os.getcwd(), "mall.db")}'
    )

class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    
    # Correct PostgreSQL scheme and accessing env var
    _db_url = os.environ.get('DATABASE_URL')
    if _db_url and _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = _db_url or 'postgresql://postgres:password@localhost:5432/mall_billing_prod'

    # Ensure SECRET_KEY is set
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Session Cookie Security
    SESSION_COOKIE_SECURE = True # Always True in Prod (Render enforces HTTPS)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Feature Flags
    CLOUD_DEMO = os.environ.get('CLOUD_DEMO', 'False').lower() == 'true'
    LOCAL_PRODUCTION = not CLOUD_DEMO


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
