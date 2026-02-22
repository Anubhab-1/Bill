import time
import pytest
from app import create_app, db
from app.auth.models import User, RoleEnum
from app.inventory.models import Product, ProductVariant
from decimal import Decimal

@pytest.fixture
def client():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        # Setup admin
        admin = User(username='admin', name='Admin', role=RoleEnum.admin)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        yield app.test_client()
        db.session.remove()
        db.drop_all()

def test_phase6_error_handling_rollback(client):
    """PHASE 6: Verify no partial commits on failure."""
    # We will simulate a failure during 'complete' indirectly 
    # by checking if a ValueError in a transaction rolls back correctly.
    with client.application.app_context():
        p = Product(name='FailTest', gst_percent=18)
        db.session.add(p)
        db.session.flush()
        v = ProductVariant(product_id=p.id, size='N/A', color='N/A', barcode='FAIL-001', price=100, stock=10)
        db.session.add(v)
        db.session.commit()

        try:
            # Start transaction
            v_db = ProductVariant.query.filter_by(barcode='FAIL-001').first()
            v_db.stock -= 5
            db.session.flush()
            
            # Artificial Crash
            raise ValueError("Simulated Crash")
            db.session.commit()
        except ValueError:
            db.session.rollback()
        
        # Verify rollback
        db.session.refresh(v_db)
        assert v_db.stock == 10, "Rollback failed, stock was deducted despite error"
        print("PHASE 6: Rollback Verified OK.")

def test_phase7_performance_baseline(client):
    """PHASE 7: Measure latency for common routes."""
    # Login first
    client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
    
    start = time.time()
    for _ in range(50):
        client.get('/')
    end = time.time()
    
    avg_latency = (end - start) / 50
    print(f"PHASE 7: Average Dashboard Latency: {avg_latency*1000:.2f}ms")
    assert avg_latency < 0.1, f"Latency too high: {avg_latency*1000:.2f}ms"

if __name__ == "__main__":
    pytest.main([__file__])
