import os
from datetime import timedelta
from sqlalchemy.pool import NullPool


def _database_url_from_env():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise RuntimeError('DATABASE_URL environment variable is not set.')
    if not db_url.startswith('postgresql://'):
        raise RuntimeError('DATABASE_URL must start with postgresql://')
    return db_url


class Config:
    """Base configuration shared across all environments."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
        # Production resilience settings
        "pool_size": 20,       # Base number of connections
        "max_overflow": 10,    # Extra connections allowed during spikes
        "pool_timeout": 30,    # Seconds to wait for a connection
    }
    # Sessions expire after 8 hours (one work shift)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Feature Flags (Default)
    CLOUD_DEMO = False
    LOCAL_PRODUCTION = False
    ALLOW_SCHEMA_FIX_ROUTE = os.environ.get('ALLOW_SCHEMA_FIX_ROUTE', 'false').lower() == 'true'

    # ── Caching ──────────────────────────────────────────────────
    CACHE_DEFAULT_TIMEOUT = 3600 # 1 hour
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Use Redis if REDIS_URL is present, otherwise fallback to SimpleCache
    if os.environ.get('REDIS_URL'):
        CACHE_TYPE = "RedisCache"
    else:
        CACHE_TYPE = "SimpleCache"

class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _database_url_from_env()

class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False

    SQLALCHEMY_DATABASE_URI = _database_url_from_env()

    # SECRET_KEY will be verified in create_app()
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Session Cookie Security
    SESSION_COOKIE_SECURE = True # Always True in Prod (Render enforces HTTPS)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Feature Flags
    CLOUD_DEMO = os.environ.get('CLOUD_DEMO', 'False').lower() == 'true'
    LOCAL_PRODUCTION = not CLOUD_DEMO


class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = _database_url_from_env()

    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": NullPool
    }
    WTF_CSRF_ENABLED = False
    WTF_CSRF_CHECK_DEFAULT = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
