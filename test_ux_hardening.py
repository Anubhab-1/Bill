
import pytest
from app import create_app, db
from app.auth.models import User
from app.billing.models import Sale, SaleItem, SalePayment, CashSession
from decimal import Decimal
from datetime import datetime, date

@pytest.fixture
def client():
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.app_context():
        db.create_all()
        # Create test user
        from app.auth.models import RoleEnum
        user = User(username='test_user', name='Test User', role=RoleEnum.admin)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        
        yield app.test_client()
        
        db.session.remove()
        db.drop_all()

def login(client):
    resp = client.post('/auth/login', data={'username': 'test_user', 'password': 'password'}, follow_redirects=True)
    assert b'Invalid username or password' not in resp.data

def test_print_queue_and_mark_printed(client):
    login(client)

    # 1. Create a Sale
    with client.application.app_context():
        # Need active session
        admin = User.query.first()
        session = CashSession(cashier_id=admin.id, start_time=datetime.now())
        db.session.add(session)
        
        sale = Sale(
            invoice_number='INV-TEST-001',
            cashier_id=admin.id,
            total_amount=Decimal('100.00'),
            gst_total=Decimal('18.00'),
            grand_total=Decimal('118.00'),
            created_at=datetime.now(),
            is_printed=False # Default
        )
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id

    # 2. Check Print Queue - Should see the sale
    resp = client.get('/billing/print-queue')
    assert resp.status_code == 200
    assert b'INV-TEST-001' in resp.data
    
    # 3. Mark as Printed
    resp = client.post(f'/billing/mark-printed/{sale_id}')
    assert resp.status_code == 204
    
    # 4. Check Print Queue - Should NOT see the sale
    resp = client.get('/billing/print-queue')
    assert resp.status_code == 200
    assert b'INV-TEST-001' not in resp.data
    assert b'All Caught Up!' in resp.data

    # 5. Verify DB
    with client.application.app_context():
        s = db.session.get(Sale, sale_id)
        assert s.is_printed == True

def test_routes_exist(client):
    login(client)
    # Just verify routes don't 404
    assert client.get('/billing/print-queue').status_code == 200
