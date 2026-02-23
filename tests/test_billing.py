import pytest
from app.inventory.models import Product, ProductVariant
from app.billing.models import Sale, SaleItem
from sqlalchemy.orm import joinedload

@pytest.fixture(scope='function')
def setup_cart_items(db_session):
    """Create some items to buy."""
    p1 = Product(name='Apple', barcode='A1', gst_percent=0)
    p2 = Product(name='Cake', barcode='C1', gst_percent=18)
    
    db_session.add_all([p1, p2])
    db_session.commit() # Commit to ensure ID is generated and visible
    
    p1_id, p2_id = p1.id, p2.id
    
    v1 = ProductVariant(product_id=p1_id, size='D', color='D', barcode='A1', price='1.00', stock=50)
    v2 = ProductVariant(product_id=p2_id, size='D', color='D', barcode='C1', price='10.00', stock=50)
    
    db_session.add_all([v1, v2])
    db_session.commit()
    return v1, v2

def test_add_item_to_cart(client, cashier_user, setup_cart_items):
    """Test scanning barcodes into the cart via session."""
    v1, v2 = setup_cart_items
    
    client.post('/auth/login', data={'username': 'testcashier', 'password': 'Cashier123'})
    
    # Needs to open cash session first
    client.post('/billing/session/open', data={'opening_cash': '100.00'}, follow_redirects=True)
    
    # Scenario: Add Apple
    resp1 = client.post('/billing/add-item', data={'barcode': 'A1'}, follow_redirects=True)
    assert resp1.status_code == 200
    
    # Scenario: Add Cake
    resp2 = client.post('/billing/add-item', data={'barcode': 'C1'}, follow_redirects=True)
    assert resp2.status_code == 200
    
    with client.session_transaction() as sess:
        cart = sess.get('cart', {})
        # Re-fetch or use ID directly to avoid DetachedInstanceError
        v1_id = v1.id
        v2_id = v2.id
        assert str(v1_id) in cart
        assert str(v2_id) in cart
        assert cart[str(v1_id)]['quantity'] == 1
        assert cart[str(v2_id)]['quantity'] == 1

def test_checkout_math_and_stock_deduction(client, cashier_user, db_session, setup_cart_items):
    """Test full checkout flow, verifying GST calculation, Subtotals, and Stock deductions."""
    v1, v2 = setup_cart_items
    v1_id, v2_id = v1.id, v2.id
    
    client.post('/auth/login', data={'username': 'testcashier', 'password': 'Cashier123'})
    client.post('/billing/session/open', data={'opening_cash': '100.00'})
    
    # Add 2 Apples ($1, 0% GST) and 1 Cake ($10, 18% GST)
    client.post('/billing/add-item', data={'barcode': 'A1'})
    client.post('/billing/add-item', data={'barcode': 'A1'}) # quantity 2
    client.post('/billing/add-item', data={'barcode': 'C1'})
    
    # Total Base: (2 * $1) + (1 * $10) = $12
    # GST Apple: 0
    # GST Cake: 10 * 0.18 = $1.80
    # Grand Total: $13.80
    
    response = client.post('/billing/complete', data={
        'payment_cash': '13.80',
        'payment_card': '0',
        'payment_upi': '0',
        'payment_loyalty': '0',
        'payment_gift': '0',
        # No discounts
        'discount_type': '',
        'discount_value': ''
    }, follow_redirects=True)
    
    assert response.status_code == 200
    
    # Check Database assertions
    sale = db_session.query(Sale).order_by(Sale.id.desc()).first()
    assert sale is not None
    assert float(sale.total_amount) == 12.00 # Subtotal
    assert float(sale.gst_total) == 1.80
    assert float(sale.grand_total) == 13.80
    
    # Verify stock deduction
    db_session.remove()
    v1 = db_session.get(ProductVariant, v1_id)
    v2 = db_session.get(ProductVariant, v2_id)
    assert v1.stock == 48 # 50 - 2
    assert v2.stock == 49 # 50 - 1

def test_checkout_insufficient_stock(client, cashier_user, db_session, setup_cart_items):
    """Test checkout fails safely when stock is depleted after adding to cart."""
    v1, _ = setup_cart_items
    v1_id = v1.id
    v1.stock = 1
    db_session.commit()
    
    v1_id = v1.id
    client.post('/auth/login', data={'username': 'testcashier', 'password': 'Cashier123'})
    client.post('/billing/session/open', data={'opening_cash': '100.00'})
    
    # Try to buy 2 (but only 1 in stock)
    client.post('/billing/add-item', data={'barcode': 'A1'})
    
    # Manually drop stock in DB
    db_session.remove()
    v1 = db_session.get(ProductVariant, v1_id)
    v1.stock = 0
    db_session.commit()
    db_session.remove() # Ensure app sees the change
    
    # 3. Try to complete
    response = client.post('/billing/complete', data={
        'payment_cash': '1.00'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Insufficient stock' in response.data
    
    # Verify no sale created
    from app.billing.models import Sale
    db_session.remove()
    assert db_session.query(Sale).count() == 0
    
    # Verify stock untouched
    db_session.remove()
    v1_reloaded = db_session.get(ProductVariant, v1_id)
    assert v1_reloaded.stock == 0
    
    # Verify target variant re-fetched successfully
    assert v1_reloaded.barcode == 'A1'
