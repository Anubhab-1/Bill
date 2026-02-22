import pytest
from app import create_app, db

def test_production_secret_key_enforcement():
    """Verify that create_app('production') raises RuntimeError if SECRET_KEY is missing."""
    import os
    from unittest.mock import patch
    
    # We patch BOTH the environment and the config dictionary in config.py
    with patch.dict(os.environ, clear=True), patch('config.config') as mock_config_dict:
        from config import ProductionConfig
        class BadProdConfig(ProductionConfig):
            SECRET_KEY = None
        
        # mock_config_dict behaves like a dict
        mock_config_dict.__getitem__.return_value = BadProdConfig
        
        with pytest.raises(RuntimeError) as exc:
            create_app('production')
        assert 'SECRET_KEY must be set' in str(exc.value)

def test_production_default_key_enforcement():
    """Verify that create_app('production') raises RuntimeError if SECRET_KEY is the default insecure one."""
    import os
    from unittest.mock import patch
    
    with patch.dict(os.environ, clear=True), patch('config.config') as mock_config_dict:
        from config import ProductionConfig
        class BadProdConfig(ProductionConfig):
            SECRET_KEY = 'dev-secret-key-change-in-production'
        
        mock_config_dict.__getitem__.return_value = BadProdConfig
        
        with pytest.raises(RuntimeError) as exc:
            create_app('production')
        assert 'SECRET_KEY must be set' in str(exc.value)

def test_csrf_enforcement():
    """Verify that POST requests fail without CSRF token in development/production."""
    # Note: testing config has CSRF disabled by default.
    # We create an app with development config for this test.
    app = create_app('development')
    client = app.test_client()
    
    with app.app_context():
        # Any POST route should return 400 Bad Request if it lacks CSRF token
        # Using /auth/login as a safe POST probe
        resp = client.post('/auth/login', data={'username': 'test', 'password': 'test'})
        assert resp.status_code == 400
        assert b"CSRF" in resp.data

if __name__ == "__main__":
    pytest.main([__file__])
