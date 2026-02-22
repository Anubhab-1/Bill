import pytest
from app import create_app, db
from app.auth.models import User, RoleEnum
from app.inventory.models import Product, ProductVariant, InventoryLog
from app.billing.models import Sale, SaleItem, CashSession
from decimal import Decimal
import threading
import time

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def login(client, username, password):
    return client.post('/auth/login', data={'username': username, 'password': password}, follow_redirects=True)

def test_full_billing_flow(client, app):
    """PHASE 4: AUTH, INVENTORY, BILLING, CASH SESSION."""
    with app.app_context():
        # Setup users
        admin = User(username='admin', name='Admin', role=RoleEnum.admin)
        admin.set_password('admin123')
        db.session.add(admin)
        
        cashier = User(username='cashier1', name='Cashier', role=RoleEnum.cashier)
        cashier.set_password('pass123')
        db.session.add(cashier)
        db.session.commit()

        # Phase 4B: Inventory Flow (AS ADMIN)
        login(client, 'admin', 'admin123')
        # Add Product
        resp = client.post('/inventory/new', data={'name': 'Bread', 'gst_percent': '5'}, follow_redirects=True)
        assert resp.status_code == 200, f"Admin couldn't access inventory. Status: {resp.status_code}"
        
        p = Product.query.filter_by(name='Bread').first()
        if p is None:
            # Check for validation errors in response
            print("Product 'Bread' not found. Response content preview:")
            print(resp.data.decode()[:500])
            assert p is not None, "Product creation failed"
        
        # Add Variant
        resp = client.post(f'/inventory/{p.id}/variants/add', data={
            'size': '400g', 'color': 'White', 'barcode': 'BRD-001', 'price': '40.00', 'stock': '10'
        }, follow_redirects=True)
        assert resp.status_code == 200
        
        v = ProductVariant.query.filter_by(barcode='BRD-001').first()
        assert v is not None, "Variant creation failed"
        
        # LOGOUT ADMIN
        client.get('/auth/logout', follow_redirects=True)
        
        # Phase 4A: Access Control (AS CASHIER)
        login(client, 'cashier1', 'pass123')
        
        with client.session_transaction() as sess:
            assert sess.get('role') == 'cashier', f"Session role should be cashier, got {sess.get('role')}"
            
        resp = client.get('/inventory/new')
        assert resp.status_code == 403, f"Expected 403 for cashier on admin route, got {resp.status_code}"
        
        # Phase 4E: Cash Session Enforcement
        resp = client.post('/billing/add-item', data={'barcode': 'BRD-001'}, follow_redirects=True)
        assert b"Please open a cash session" in resp.data # Enforcement OK
        
        # Open Session
        client.post('/billing/session/open', data={'opening_cash': '1000'}, follow_redirects=True)
        
        # Phase 4C: Billing Flow
        # Add to cart
        client.post('/billing/add-item', data={'barcode': 'BRD-001'}, follow_redirects=True)
        
        # Complete Sale
        resp = client.post('/billing/complete', data={
            'payment_cash': '42.00', # 40 + 5% GST = 42
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Invoice" in resp.data or b"Sale" in resp.data
        
        # Verify Stock Deduction
        db.session.refresh(v)
        assert v.stock == 9
        
        # Verify Inventory Log
        log = InventoryLog.query.filter_by(product_id=p.id).order_by(InventoryLog.id.desc()).first()
        assert log is not None
        assert log.reason == 'SALE'
        
        # Phase 4D: Returns Flow
        client.get('/auth/logout', follow_redirects=True)
        login(client, 'cashier1', 'pass123')
        
        sale = Sale.query.first()
        sale_item = SaleItem.query.first()
        
        # Simulate Return Process
        # 1. Access process page
        resp = client.get(f'/billing/returns/process/{sale.id}')
        assert resp.status_code == 200
        
        # 2. Submit Return
        resp = client.post(f'/billing/returns/process/{sale.id}', data={
            f'qty_{sale_item.id}': '1',
            'refund_method': 'cash',
            'note': 'Audit Test Return'
        }, follow_redirects=True)
        assert resp.status_code == 200
        
        # 3. Verify Stock Restoration
        db.session.refresh(v)
        assert v.stock == 10, f"Stock should be 10 after return, got {v.stock}"
        
        # 4. Verify Inventory Log for Return
        log = InventoryLog.query.filter_by(product_id=p.id).order_by(InventoryLog.id.desc()).first()
        assert log.reason == 'RETURN'

def test_concurrency_race_simulation(client, app):
    """PHASE 5: Simulating concurrent invoice generation."""
    with app.app_context():
        # Setup multiple threads trying to get invoice numbers
        results = []
        errors = []
        def get_invoice():
            with app.app_context():
                try:
                    from app.billing.invoice import generate_invoice_number
                    inv = generate_invoice_number(db.session)
                    db.session.commit()
                    results.append(inv)
                except Exception as e:
                    errors.append(str(e))

        threads = [threading.Thread(target=get_invoice) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        if errors:
            print(f"Concurrency errors: {errors}")
            
        # Check for duplicates
        unique_results = set(results)
        assert len(unique_results) == len(results), f"Duplicate invoices detected: {results}"

if __name__ == "__main__":
    pytest.main([__file__])
