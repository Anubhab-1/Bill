"""
test_batches.py — Tests for ProductBatch model and FIFO billing.

Run: pytest test_batches.py -v
"""
import os
os.environ['FLASK_RUN_FROM_CLI'] = '1'

import pytest
from datetime import date, timedelta

from app import create_app, db
from app.inventory.models import Product, ProductBatch
from app.auth.models import User, RoleEnum


@pytest.fixture(scope='function')
def client():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        # Seed admin user
        user = User(username='admin', name='Admin', role=RoleEnum.admin)
        user.set_password('admin123')
        db.session.add(user)
        db.session.commit()
        yield app.test_client()
        db.drop_all()


def login(client):
    resp = client.post('/auth/login',
                       data={'username': 'admin', 'password': 'admin123'},
                       follow_redirects=True)
    # Fail loudly if login failed
    assert b'Invalid' not in resp.data, "Login failed"
    return resp


# ── Helper: create a product + batches ─────────────────────────────────────

def make_product_with_batches(app_ctx):
    """Creates product with two batches for FIFO testing."""
    p = Product(name='Test Cookie', barcode='TEST001', price=100, stock=20, gst_percent=5)
    db.session.add(p)
    db.session.flush()

    today = date.today()
    batch_old = ProductBatch(
        product_id=p.id,
        batch_number='BATCH-A',
        expiry_date=today + timedelta(days=10),  # expires sooner → should be consumed first
        quantity=10,
        cost_price=80,
    )
    batch_new = ProductBatch(
        product_id=p.id,
        batch_number='BATCH-B',
        expiry_date=today + timedelta(days=20),  # expires later
        quantity=10,
        cost_price=80,
    )
    db.session.add_all([batch_old, batch_new])
    db.session.commit()
    return p, batch_old, batch_new


# ── 1. FIFO consumption test ────────────────────────────────────────────────

def test_fifo_batch_consumption(client):
    """
    Selling 15 units should consume 10 from BATCH-A (earliest exp) first,
    then 5 from BATCH-B.
    """
    with client.application.app_context():
        product, batch_a, batch_b = make_product_with_batches(client.application.app_context())

        # Simulate FIFO deduction (same logic as billing complete())
        qty_to_sell = 15
        product.stock -= qty_to_sell

        fifo_batches = (
            ProductBatch.query
            .filter_by(product_id=product.id)
            .filter(ProductBatch.quantity > 0)
            .order_by(
                db.case((ProductBatch.expiry_date.is_(None), 1), else_=0),
                ProductBatch.expiry_date.asc()
            )
            .all()
        )

        remaining = qty_to_sell
        for b in fifo_batches:
            if remaining <= 0:
                break
            take = min(b.quantity, remaining)
            b.quantity -= take
            remaining -= take

        db.session.commit()

        batch_a_fresh = db.session.get(ProductBatch, batch_a.id)
        batch_b_fresh = db.session.get(ProductBatch, batch_b.id)

        assert batch_a_fresh.quantity == 0,  f"BATCH-A should be empty, got {batch_a_fresh.quantity}"
        assert batch_b_fresh.quantity == 5,  f"BATCH-B should have 5 left, got {batch_b_fresh.quantity}"
        assert remaining == 0, "No leftover — all units allocated"


# ── 2. Model helpers ────────────────────────────────────────────────────────

def test_batch_is_expired():
    """ProductBatch.is_expired returns True when expiry_date is in the past."""
    b = ProductBatch(expiry_date=date.today() - timedelta(days=1))
    assert b.is_expired is True

def test_batch_not_expired():
    b = ProductBatch(expiry_date=date.today() + timedelta(days=5))
    assert b.is_expired is False

def test_batch_no_expiry():
    b = ProductBatch(expiry_date=None)
    assert b.is_expired is False
    assert b.days_to_expiry is None

def test_days_to_expiry():
    b = ProductBatch(expiry_date=date.today() + timedelta(days=14))
    assert b.days_to_expiry == 14


# ── 3. Routes exist (with auth) ─────────────────────────────────────────────

def test_batch_view_route(client):
    """GET /inventory/<id>/batches → 200 for existing product."""
    login(client)
    with client.application.app_context():
        p = Product(name='Snack', barcode='SNACK001', price=50, stock=5, gst_percent=0)
        db.session.add(p)
        db.session.commit()
        pid = p.id

    resp = client.get(f'/inventory/{pid}/batches')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


def test_add_batch_route_get(client):
    """GET /inventory/<id>/batches/add → 200 for admin."""
    login(client)
    with client.application.app_context():
        p = Product(name='Snack2', barcode='SNACK002', price=50, stock=5, gst_percent=0)
        db.session.add(p)
        db.session.commit()
        pid = p.id

    resp = client.get(f'/inventory/{pid}/batches/add')
    assert resp.status_code == 200


def test_add_batch_increases_stock(client):
    """POST to add_batch increases product.stock and creates ProductBatch."""
    login(client)
    with client.application.app_context():
        p = Product(name='Snack3', barcode='SNACK003', price=50, stock=10, gst_percent=0)
        db.session.add(p)
        db.session.commit()
        pid = p.id

    today = date.today()
    expiry = (today + timedelta(days=60)).strftime('%Y-%m-%d')
    resp = client.post(f'/inventory/{pid}/batches/add', data={
        'batch_number': 'B-TEST',
        'expiry_date': expiry,
        'quantity': '25',
        'cost_price': '40',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        p_fresh = db.session.get(Product, pid)
        assert p_fresh.stock == 35, f"Expected 35, got {p_fresh.stock}"
        batch = ProductBatch.query.filter_by(product_id=pid, batch_number='B-TEST').first()
        assert batch is not None
        assert batch.quantity == 25


# ── 4. Expiry alert visibility ──────────────────────────────────────────────

def test_dashboard_expiry_alert_visible(client):
    """Dashboard shows expiry warning for a batch expiring in <14 days."""
    login(client)
    with client.application.app_context():
        p = Product(name='ExpiryTest', barcode='EXP001', price=20, stock=5, gst_percent=0)
        db.session.add(p)
        db.session.flush()
        b = ProductBatch(
            product_id=p.id,
            batch_number='EXP-BATCH',
            expiry_date=date.today() + timedelta(days=3),
            quantity=5,
            cost_price=15,
        )
        db.session.add(b)
        db.session.commit()

    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Expiring Within 14 Days' in resp.data or b'EXP-BATCH' in resp.data, \
        "Dashboard should show expiry warning"
