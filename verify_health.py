
import pytest
from app import create_app
from flask import json

@pytest.fixture
def client():
    app = create_app('testing')
    with app.test_client() as client:
        yield client

def test_health_json(client):
    """Test standard JSON response for load balancers."""
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert 'db' in data['details']
    assert 'disk_free_percent' in data['details']
    print("\n✅ /health JSON Check Passed")

def test_health_htmx(client):
    """Test HTMX HTML response for dashboard widget."""
    resp = client.get('/health', headers={'HX-Request': 'true'})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<div' in html
    assert 'Database' in html
    assert 'Disk Space' in html
    print("✅ /health HTMX Check Passed")

if __name__ == "__main__":
    # Manual run wrapper
    try:
        app = create_app('testing')
        with app.test_client() as client:
            test_health_json(client)
            test_health_htmx(client)
    except Exception as e:
        print(f"\n❌ Verification Failed: {e}")
        exit(1)
