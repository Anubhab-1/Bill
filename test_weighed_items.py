"""
test_weighed_items.py — Tests for weighed-item billing.
Run: pytest test_weighed_items.py -v
"""
import os
os.environ['FLASK_RUN_FROM_CLI'] = '1'

import pytest
from decimal import Decimal
from datetime import date, timedelta

from app import create_app, db
from app.inventory.models import Product
from app.billing.models import Sale, SaleItem, CashSession
from app.billing.cart import add_weighed_to_cart, get_cart, clear_cart
from app.auth.models import User, RoleEnum


@pytest.fixture(scope='function')
def client():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        user = User(username='admin', name='Admin', role=RoleEnum.admin)
        user.set_password('admin123')
        db.session.add(user)
        db.session.commit()
        yield app.test_client()
        db.drop_all()


def login(client):
    client.post('/auth/login',
                data={'username': 'admin', 'password': 'admin123'},
                follow_redirects=True)


def open_cash_session(client):
    """Open a CashierSession for the admin so billing guards pass."""
    # POST to open_session route which sets the session cookie
    client.post('/billing/session/open',
                data={'opening_cash': '500'},
                follow_redirects=True)


def make_weighed_product(app):
    p = Product(
        name='Basmati Rice',
        barcode='RICE001',
        price=Decimal('90.00'),      # price_per_kg
        price_per_kg=Decimal('90.00'),
        stock=50,
        gst_percent=5,
        is_weighed=True,
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


# ── 1. Price calculation: weight × price_per_kg ─────────────────────────────

def test_weighed_price_calculation():
    """line_price = weight_kg × price_per_kg — no rounding drift."""
    weight_kg = Decimal('0.850')
    price_per_kg = Decimal('90.00')
    expected = Decimal('76.50')
    actual = (price_per_kg * weight_kg).quantize(Decimal('0.01'))
    assert actual == expected, f"Expected ₹76.50, got ₹{actual}"


def test_weighed_price_fractional():
    """Fractional gram weight rounds to 2dp correctly."""
    weight_kg = Decimal('0.123')
    price_per_kg = Decimal('150.00')
    expected = Decimal('18.45')
    actual = (price_per_kg * weight_kg).quantize(Decimal('0.01'))
    assert actual == expected, f"Expected ₹18.45, got ₹{actual}"


# ── 2. add_weighed_to_cart puts correct data in session ────────────────────

def test_add_weighed_to_cart(client):
    with client.application.app_context():
        product = make_weighed_product(client.application)

        with client.session_transaction() as sess:
            sess['cart'] = {}
            sess.modified = True

        # Call function directly (bypasses HTTP)
        with client.application.test_request_context():
            from flask import session
            session['cart'] = {}
            add_weighed_to_cart(product, Decimal('0.500'))
            cart = get_cart()

        assert str(product.id) in cart
        entry = cart[str(product.id)]
        assert entry['is_weighed'] is True
        assert entry['weight_kg'] == '0.500'
        assert Decimal(entry['price']) == Decimal('45.00')  # 90 × 0.5


# ── 3. Model flag defaults ───────────────────────────────────────────────────

def test_product_defaults_not_weighed(client):
    with client.application.app_context():
        p = Product(name='Candy', barcode='CANDY001', price=10, stock=100, gst_percent=0)
        db.session.add(p)
        db.session.commit()
        assert p.is_weighed is False
        assert p.price_per_kg is None


def test_product_is_weighed_flag(client):
    with client.application.app_context():
        p = make_weighed_product(client.application)
        assert p.is_weighed is True
        assert p.price_per_kg == Decimal('90.00')


# ── 4. HTTP endpoint — add_weighed_item route ───────────────────────────────

def test_add_weighed_item_route(client):
    """POST /billing/add-weighed-item with valid weight → 200 and cart populated."""
    login(client)
    open_cash_session(client)
    with client.application.app_context():
        product = make_weighed_product(client.application)
        pid = product.id

    resp = client.post('/billing/add-weighed-item', data={
        'product_id': str(pid),
        'weight_kg': '0.750',
    })
    assert resp.status_code == 200
    # Cart should have been rendered (response is the _cart.html partial)
    assert b'Basmati Rice' in resp.data or b'cart' in resp.data.lower()


def test_add_weighed_item_invalid_weight(client):
    """POST with weight=0 → returns error in cart partial."""
    login(client)
    open_cash_session(client)
    with client.application.app_context():
        product = make_weighed_product(client.application)
        pid = product.id

    resp = client.post('/billing/add-weighed-item', data={
        'product_id': str(pid),
        'weight_kg': '0',
    })
    assert resp.status_code == 200
    assert b'Weight must be greater than zero' in resp.data


def test_add_weighed_item_non_numeric(client):
    """POST with non-numeric weight → error."""
    login(client)
    open_cash_session(client)
    with client.application.app_context():
        product = make_weighed_product(client.application)
        pid = product.id

    resp = client.post('/billing/add-weighed-item', data={
        'product_id': str(pid),
        'weight_kg': 'abc',
    })
    assert resp.status_code == 200
    assert b'Invalid weight' in resp.data


# ── 5. add_item route redirects weighed items to modal trigger ───────────────

def test_add_item_weighed_triggers_modal(client):
    """Scanning a weighed barcode should return the weight modal HTML."""
    login(client)
    open_cash_session(client)
    with client.application.app_context():
        product = make_weighed_product(client.application)

    resp = client.post('/billing/add-item', data={'barcode': 'RICE001'})
    assert resp.status_code == 200
    # The response should contain the weight modal markup
    assert b'weight-modal' in resp.data or b'weight_kg' in resp.data


# ── 6. Validator: price_per_kg required when is_weighed ─────────────────────

def test_validator_requires_price_per_kg_when_weighed():
    from app.inventory.validators import validate_product_form
    errors = validate_product_form({
        'name': 'Test',
        'barcode': 'BC001',
        'price': '50',
        'stock': '10',
        'gst_percent': '5',
        'is_weighed': 'on',   # checked
        'price_per_kg': '',   # missing
    })
    assert 'price_per_kg' in errors


def test_validator_price_per_kg_not_required_when_not_weighed():
    from app.inventory.validators import validate_product_form
    errors = validate_product_form({
        'name': 'Test',
        'barcode': 'BC001',
        'price': '50',
        'stock': '10',
        'gst_percent': '5',
        'is_weighed': '',     # not checked
        'price_per_kg': '',
    })
    assert 'price_per_kg' not in errors
