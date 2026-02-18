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
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:password@localhost:5432/mall_billing_prod'
    )

    # In production, ensure SECRET_KEY is set via environment variable
    # If not set, this will raise an error during app startup (handled in create_app)
    @property
    def SECRET_KEY(self):
        key = os.environ.get('SECRET_KEY')
        if not key:
            raise ValueError("SECRET_KEY environment variable is required in production!")
        return key

    SESSION_COOKIE_SECURE = False  # Set to True if serving over HTTPS (recommended)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Cloud Demo Mode: Disables backups and sensitive file operations
    @property
    def CLOUD_DEMO(self):
        return os.environ.get('CLOUD_DEMO', 'False').lower() == 'true'

    @property
    def LOCAL_PRODUCTION(self):
        return not self.CLOUD_DEMO


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
