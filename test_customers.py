
import pytest
from decimal import Decimal
from app import create_app, db
from app.auth.models import User, RoleEnum
from app.inventory.models import Product, ProductVariant
from app.customers.models import Customer, GiftCard
from app.billing.models import Sale, SalePayment, CashSession

@pytest.fixture
def client(app):
    """Uses the global app fixture and seeds initial test data."""
    with app.app_context():
        # setup_database (from conftest) already ran db.create_all()
        
        # Setup User/Admin
        admin = User(username='admin', name='Admin User', role=RoleEnum.admin)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush() # Generate ID
        
        # Setup Product & Variant
        p1 = Product(name="Test Item", barcode="P123", gst_percent=0)
        db.session.add(p1)
        db.session.flush()
        
        v1 = ProductVariant(
            product_id=p1.id, 
            barcode="123456", 
            price=Decimal("100.00"), 
            stock=100,
            size="NA",
            color="NA"
        )
        db.session.add(v1)
        
        # Setup Cash Session
        session = CashSession(cashier_id=admin.id, opening_cash=Decimal("1000.00"))
        db.session.add(session)
        
        db.session.commit()
        
        # Return test client
        with app.test_client() as client:
            # Login
            client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
            yield client

def test_create_and_search_customer(client):
    # Create
    resp = client.post('/customers/create', json={
        'name': 'John Doe',
        'phone': '9876543210'
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['name'] == 'John Doe'
    
    # Search
    resp = client.get('/customers/search?q=9876')
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['name'] == 'John Doe'

def test_accrue_points(client):
    # Create customer
    client.post('/customers/create', json={'name': 'Loyal User', 'phone': '1112223333'})
    cust = Customer.query.filter_by(phone='1112223333').first()
    cust_id = cust.id
    
    # Attach customer
    client.post('/billing/customer/attach', data={'customer_id': cust_id})
    
    # Add Item (Price 100)
    with client.session_transaction() as sess:
        # Simulate cart manually because route logic is complex with HTMX
        # But we can use the add-item route
        pass
    
    client.post('/billing/add-item', data={'barcode': '123456'})
    
    # Complete Sale
    # Total 100. Should earn 1 point.
    resp = client.post('/billing/complete', data={
        'payment_cash': '100'
    })
    assert resp.status_code == 302 # Redirect to invoice
    
    # Verify points
    cust = db.session.get(Customer, cust_id)
    assert cust.points == 1

def test_redeem_points(client):
    # Setup customer with points
    cust = Customer(name="Rich User", phone="5555555555", points=50) # ₹50 worth
    db.session.add(cust)
    db.session.commit()
    cust_id = cust.id
    
    client.post('/billing/customer/attach', data={'customer_id': cust_id})
    client.post('/billing/add-item', data={'barcode': '123456'}) # ₹100 item
    
    # Pay 50 Cash + 50 Points
    resp = client.post('/billing/complete', data={
        'payment_cash': '50',
        'payment_loyalty': '50'
    })
    assert resp.status_code == 302
    
    # Verify points deducted
    cust = db.session.get(Customer, cust_id)
    assert cust.points == 1 # 0 (balance post-redemption) + 1 (accrued from 100 total)

def test_gift_card_redemption(client):
    # Issue Gift Card
    gc = GiftCard(code="GIFT100", initial_balance=100, balance=100)
    db.session.add(gc)
    db.session.commit()
    gc_id = gc.id
    
    client.post('/billing/add-item', data={'barcode': '123456'}) # ₹100 item
    
    # Pay with Gift Card
    resp = client.post('/billing/complete', data={
        'payment_gift': '100',
        'gift_card_code': 'GIFT100'
    })
    assert resp.status_code == 302
    
    # Verify GC balance
    gc = db.session.get(GiftCard, gc_id)
    assert gc.balance == 0
    assert gc.initial_balance == 100

