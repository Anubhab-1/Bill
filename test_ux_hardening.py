
import pytest
from app import create_app, db
from app.auth.models import User
from app.billing.models import Sale, SaleItem, SalePayment, CashSession
from decimal import Decimal
from datetime import datetime, date

@pytest.fixture
def client(app):
    """Uses global app fixture and seeds test user."""
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.app_context():
        # setup_database (from conftest) already ran db.create_all()
        from app.auth.models import RoleEnum
        user = User(username='test_user', name='Test User', role=RoleEnum.admin)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        
        with app.test_client() as client:
            yield client

def login(client):
    resp = client.post('/auth/login', data={'username': 'test_user', 'password': 'password'}, follow_redirects=True)
    assert b'Invalid username or password' not in resp.data

def open_cash_session(client):
    """Open a CashierSession for the test user so billing guards pass."""
    client.post('/billing/session/open',
                data={'opening_cash': '500'},
                follow_redirects=True)

def test_print_queue_and_mark_printed(client):
    login(client)
    open_cash_session(client)

    # 1. Create a Sale
    with client.application.app_context():
        # Need active session
        admin = User.query.first()
        session = CashSession(
            cashier_id=admin.id,
            opening_cash=Decimal('1000.00'),
            system_total=Decimal('0.00'),
            start_time=datetime.now()
        )
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
    assert resp.status_code == 200
    
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
    open_cash_session(client)
    # Just verify routes don't 404
    assert client.get('/billing/print-queue').status_code == 200
