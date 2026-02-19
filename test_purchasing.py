"""
test_purchasing.py — Tests for the Supplier & Purchase Order system.
Run: pytest test_purchasing.py -v
"""
import os
os.environ['FLASK_RUN_FROM_CLI'] = '1'

import pytest
from decimal import Decimal
from datetime import date, timedelta

from app import create_app, db
from app.inventory.models import Product, ProductBatch, InventoryLog
from app.billing.models import Sale
from app.auth.models import User, RoleEnum
from app.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderItem,
    GoodsReceipt, GoodsReceiptItem, POStatus
)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope='function')
def client():
    app = create_app('testing')
    with app.app_context():
        db.create_all()

        # Admin user
        admin = User(username='admin', name='Admin', role=RoleEnum.admin)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

        yield app.test_client()
        db.drop_all()


def login(client):
    client.post('/auth/login',
                data={'username': 'admin', 'password': 'admin123'},
                follow_redirects=True)


def make_supplier(name='Metro Wholesale'):
    s = Supplier(name=name, contact='9900001111', gst_no='27AAPFU0939F1ZV')
    db.session.add(s)
    db.session.commit()
    return s


def make_product(name='Basmati Rice', stock=10):
    p = Product(
        name=name,
        barcode=f'BC_{name[:5].upper()}',
        price=Decimal('100.00'),
        stock=stock,
        gst_percent=5,
        is_active=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


def make_po(supplier_id, product_id, qty=10, cost=Decimal('80.00')):
    po = PurchaseOrder(
        supplier_id=supplier_id,
        status=POStatus.DRAFT,
    )
    db.session.add(po)
    db.session.flush()
    item = PurchaseOrderItem(
        po_id=po.id,
        product_id=product_id,
        ordered_qty=qty,
        unit_cost=cost,
    )
    db.session.add(item)
    db.session.commit()
    return po


# ── 1. Supplier creation ─────────────────────────────────────────

def test_create_supplier(client):
    with client.application.app_context():
        s = make_supplier('Fresh Farms Ltd.')
        assert s.id is not None
        assert s.name == 'Fresh Farms Ltd.'
        assert s.is_active is True


def test_supplier_list_route(client):
    login(client)
    resp = client.get('/purchasing/suppliers')
    assert resp.status_code == 200


def test_new_supplier_route_post(client):
    login(client)
    resp = client.post('/purchasing/suppliers/new', data={
        'name': 'Quick Traders',
        'contact': '9876543210',
        'gst_no': '29AABCT1234E1ZK',
        'address': '123 Market St',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with client.application.app_context():
        s = Supplier.query.filter_by(name='Quick Traders').first()
        assert s is not None
        assert s.gst_no == '29AABCT1234E1ZK'


# ── 2. PO creation ────────────────────────────────────────────────

def test_create_po_model(client):
    with client.application.app_context():
        s = make_supplier()
        p = make_product()
        po = make_po(s.id, p.id, qty=20, cost=Decimal('90.00'))
        assert po.status == POStatus.DRAFT
        assert len(po.items) == 1
        assert po.items[0].ordered_qty == 20
        assert po.total_cost == Decimal('1800.00')


def test_create_po_route(client):
    login(client)
    with client.application.app_context():
        s = make_supplier()
        p = make_product()
        sid = s.id
        pid = p.id

    resp = client.post('/purchasing/new', data={
        'supplier_id': str(sid),
        'expected_date': str(date.today() + timedelta(days=7)),
        'notes': 'Rush order',
        'product_id[]': [str(pid)],
        'ordered_qty[]': ['5'],
        'unit_cost[]': ['75.00'],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with client.application.app_context():
        po = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).first()
        assert po is not None
        assert po.supplier_id == sid
        assert len(po.items) == 1
        assert po.items[0].ordered_qty == 5


# ── 3. PO status transitions ──────────────────────────────────────

def test_send_po(client):
    login(client)
    with client.application.app_context():
        s = make_supplier()
        p = make_product()
        po = make_po(s.id, p.id)
        po_id = po.id

    resp = client.post(f'/purchasing/{po_id}/send', follow_redirects=True)
    assert resp.status_code == 200
    with client.application.app_context():
        po = db.session.get(PurchaseOrder, po_id)
        assert po.status == POStatus.SENT


def test_cancel_po(client):
    login(client)
    with client.application.app_context():
        s = make_supplier()
        p = make_product()
        po = make_po(s.id, p.id)
        po.status = POStatus.SENT
        db.session.commit()
        po_id = po.id

    resp = client.post(f'/purchasing/{po_id}/cancel', follow_redirects=True)
    assert resp.status_code == 200
    with client.application.app_context():
        po = db.session.get(PurchaseOrder, po_id)
        assert po.status == POStatus.CANCELLED


# ── 4. GRN — stock increase + InventoryLog ────────────────────────

def test_grn_increases_stock(client):
    """Full GRN: stock goes up by received qty, log created, status → RECEIVED."""
    login(client)
    with client.application.app_context():
        s = make_supplier()
        p = make_product(stock=5)
        po = make_po(s.id, p.id, qty=10)
        po.status = POStatus.SENT
        db.session.commit()
        po_id  = po.id
        item   = po.items[0]

    resp = client.post(f'/purchasing/{po_id}/receive', data={
        f'qty_{item.id}': '10',
        f'batch_{item.id}': 'BATCH-001',
        f'expiry_{item.id}': str(date.today() + timedelta(days=180)),
        'notes': 'Full delivery',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        p_db  = Product.query.get(item.product_id)
        po_db = db.session.get(PurchaseOrder, po_id)

        # Stock updated
        assert p_db.stock == 15   # 5 original + 10 received

        # PO fully received
        assert po_db.status == POStatus.RECEIVED

        # InventoryLog created
        log = (InventoryLog.query
               .filter_by(product_id=p_db.id)
               .order_by(InventoryLog.id.desc())
               .first())
        assert log is not None
        assert 'GRN' in log.reason
        assert log.old_stock == 5
        assert log.new_stock == 15


def test_grn_creates_product_batch(client):
    """GRN should create a ProductBatch record."""
    login(client)
    with client.application.app_context():
        s = make_supplier()
        p = make_product(stock=0)
        po = make_po(s.id, p.id, qty=20)
        po.status = POStatus.SENT
        db.session.commit()
        po_id = po.id
        item  = po.items[0]

    resp = client.post(f'/purchasing/{po_id}/receive', data={
        f'qty_{item.id}': '20',
        f'batch_{item.id}': 'BATCH-XYZ',
        f'expiry_{item.id}': str(date.today() + timedelta(days=90)),
        'notes': '',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        batch = ProductBatch.query.filter_by(
            product_id=item.product_id,
            batch_number='BATCH-XYZ',
        ).first()
        assert batch is not None
        assert batch.quantity == 20


def test_partial_grn_sets_status_partial(client):
    """Receiving only part of the ordered qty → PO status = PARTIAL."""
    login(client)
    with client.application.app_context():
        s = make_supplier()
        p = make_product(stock=0)
        po = make_po(s.id, p.id, qty=10)
        po.status = POStatus.SENT
        db.session.commit()
        po_id = po.id
        item  = po.items[0]

    resp = client.post(f'/purchasing/{po_id}/receive', data={
        f'qty_{item.id}': '4',   # only 4 of 10
        f'batch_{item.id}': '',
        f'expiry_{item.id}': '',
        'notes': '',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        po_db = db.session.get(PurchaseOrder, po_id)
        assert po_db.status == POStatus.PARTIAL
        # second GRN available
        assert po_db.items[0].remaining_qty == 6


def test_grn_empty_qty_rejected(client):
    """Submitting all zeros → 200 with error, no GRN created."""
    login(client)
    with client.application.app_context():
        s = make_supplier()
        p = make_product(stock=0)
        po = make_po(s.id, p.id, qty=10)
        po.status = POStatus.SENT
        db.session.commit()
        po_id = po.id
        item  = po.items[0]

    resp = client.post(f'/purchasing/{po_id}/receive', data={
        f'qty_{item.id}': '0',
        f'batch_{item.id}': '',
        f'expiry_{item.id}': '',
        'notes': '',
    })
    assert resp.status_code == 200
    with client.application.app_context():
        assert GoodsReceipt.query.filter_by(po_id=po_id).count() == 0


# ── 5. PO helpers ─────────────────────────────────────────────────

def test_po_is_overdue(client):
    with client.application.app_context():
        s = make_supplier()
        p = make_product()
        po = make_po(s.id, p.id)
        po.expected_date = date.today() - timedelta(days=1)
        po.status = POStatus.SENT
        db.session.commit()
        assert po.is_overdue is True


def test_po_not_overdue_when_received(client):
    with client.application.app_context():
        s = make_supplier()
        p = make_product()
        po = make_po(s.id, p.id)
        po.expected_date = date.today() - timedelta(days=1)
        po.status = POStatus.RECEIVED
        db.session.commit()
        assert po.is_overdue is False
