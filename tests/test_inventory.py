import pytest
from app.inventory.models import Product, ProductVariant

def test_inventory_list_requires_login(client):
    """Test that unauthorized users are redirected."""
    response = client.get('/inventory/')
    assert response.status_code == 302
    assert b'/auth/login' in response.data

def test_add_product_success(client, admin_user, db_session):
    """Test adding a new product via the API."""
    client.post('/auth/login', data={'username': 'testadmin', 'password': 'Admin123'})
    
    response = client.post('/inventory/new', data={
        'name': 'Test Cola',
        'price': '2.50',
        'stock': '100',
        'gst_percent': '18'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    
    # Verify in database
    db_session.remove()
    product = db_session.query(Product).filter_by(name='Test Cola').first()
    assert product is not None
    assert product.name == 'Test Cola'

def test_edit_product(client, admin_user, db_session):
    """Test editing an existing product."""
    client.post('/auth/login', data={'username': 'testadmin', 'password': 'Admin123'})
    
    # 1. Create a product directly in DB for speed and reliability in this test
    p = Product(name='Editable', barcode='EDIT1', gst_percent=0)
    db_session.add(p)
    db_session.commit()
    product_id = p.id
    db_session.remove()
    
    # 2. Edit it via client
    response = client.post(f'/inventory/{product_id}/edit', data={
        'name': 'Changed Name',
        'price': '15.00',
        'stock': '20',
        'gst_percent': '5',
        'is_weighed': '0'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    
    # 3. Verify
    db_session.remove()
    p_updated = db_session.get(Product, product_id)
    assert p_updated.name == 'Changed Name'
    assert p_updated.gst_percent == 5

def test_delete_product(client, admin_user, db_session):
    """Test soft-deleting a product."""
    client.post('/auth/login', data={'username': 'testadmin', 'password': 'Admin123'})
    
    # 1. Create directly
    p = Product(name='Deletable', barcode='DEL1', gst_percent=0)
    db_session.add(p)
    db_session.commit()
    product_id = p.id
    db_session.remove()
    
    # 2. Delete via client
    response = client.post(f'/inventory/{product_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    
    # 3. Verify
    db_session.remove()
    p_deleted = db_session.get(Product, product_id)
    assert p_deleted.is_active is False
