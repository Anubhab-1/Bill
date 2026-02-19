
import pytest
from decimal import Decimal
from datetime import date, timedelta
from app import create_app, db
from app.auth.models import User, RoleEnum
from app.billing.models import Sale, SaleItem, SalePayment
from app.inventory.models import Product

# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope='function')
def client():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
    with app.app_context():
        db.create_all()
        
        # Create Admin
        admin = User(username='admin', name='Admin', role=RoleEnum.admin)
        admin.set_password('admin123')
        db.session.add(admin)
        
        # Create Cashier (for access control test)
        cashier = User(username='cashier1', name='Cashier', role=RoleEnum.cashier)
        cashier.set_password('password')
        db.session.add(cashier)
        
        db.session.commit()
        
        yield app.test_client()
        db.session.remove()
        db.drop_all()

@pytest.fixture
def app(client):
    """Return the Flask app instance from the client."""
    return client.application

def login(client, username, password):
    return client.post('/auth/login', data={'username': username, 'password': password}, follow_redirects=True)

# ── Tests ─────────────────────────────────────────────────────────

def test_reporting_access_denied_for_non_admin(client):
    """Ensure non-admin users cannot access reports."""
    login(client, 'cashier1', 'password')
    
    routes = [
        '/reporting/',
        '/reporting/sales',
        '/reporting/gst',
        '/reporting/inventory',
        '/reporting/export/sales'
    ]
    
    for route in routes:
        response = client.get(route)
        assert response.status_code == 403, f"Access to {route} should be forbidden"

def test_reporting_access_granted_for_admin(client):
    """Ensure admin users can access reports."""
    login(client, 'admin', 'admin123')
    response = client.get('/reporting/')
    assert response.status_code == 200
    assert b"Business intelligence" in response.data

def test_sales_report_data(client, app):
    """Test that sales data appears correctly in the report."""
    login(client, 'admin', 'admin123')
    
    with app.app_context():
        # Create a product
        p = Product(name="Test Report Item", barcode="RPT001", price=Decimal("100.00"), stock=10, gst_percent=18)
        db.session.add(p)
        db.session.commit()
        
        # Create sale
        s = Sale(
            invoice_number="INV-RPT-001",
            cashier_id=1,
            total_amount=Decimal("118.00"), # 100 + 18% GST
            gst_total=Decimal("18.00")
        )
        db.session.add(s)
        db.session.commit()
        
        # Add item
        si = SaleItem(
            sale_id=s.id, 
            product_id=p.id, 
            quantity=1, 
            price_at_sale=Decimal("100.00"), 
            subtotal=Decimal("100.00"),
            gst_percent=18
        )
        db.session.add(si)
        
        # Add payment
        sp = SalePayment(sale_id=s.id, payment_method="CASH", amount=Decimal("118.00"))
        db.session.add(sp)
        db.session.commit()

    # Get report
    response = client.get('/reporting/sales')
    assert response.status_code == 200
    assert b"INV-RPT-001" in response.data
    assert b"118.00" in response.data

def test_inventory_report_data(client, app):
    """Test inventory valuation."""
    login(client, 'admin', 'admin123')
    
    with app.app_context():
        p = Product(name="Valuation Item", barcode="VAL001", price=Decimal("50.00"), stock=20, gst_percent=5, is_active=True)
        db.session.add(p)
        db.session.commit()
        # Value = 20 * 50 = 1000.00
    
    response = client.get('/reporting/inventory')
    assert response.status_code == 200
    assert b"Valuation Item" in response.data
    assert b"1,000.00" in response.data

def test_csv_export(client, app):
    """Test CSV export functionality."""
    login(client, 'admin', 'admin123')
    
    with app.app_context():
         # Create a sale to have some data
        s = Sale(invoice_number="EXP-001", cashier_id=1, total_amount=Decimal("50.00"), gst_total=Decimal("0.00"))
        db.session.add(s)
        db.session.commit()

    response = client.get('/reporting/export/sales')
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/csv"
    assert b"Invoice #" in response.data
    assert b"EXP-001" in response.data
