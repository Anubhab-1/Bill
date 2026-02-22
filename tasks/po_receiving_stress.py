import importlib
import os
import threading
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv


load_dotenv()


def _resolve_test_database_url() -> str:
    explicit = os.environ.get('TEST_DATABASE_URL')
    if explicit:
        return explicit
    base = os.environ.get('DATABASE_URL')
    if not base:
        raise RuntimeError('Set TEST_DATABASE_URL or DATABASE_URL before running tests.')
    if not base.startswith('postgresql://'):
        raise RuntimeError('DATABASE_URL must start with postgresql://')
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, parts.netloc, '/mall_test', parts.query, parts.fragment))


def _make_app(tmp_path):
    test_database_url = _resolve_test_database_url()
    if not test_database_url.startswith('postgresql://'):
        raise RuntimeError('TEST_DATABASE_URL must start with postgresql://')
    os.environ['DATABASE_URL'] = test_database_url

    app_mod = importlib.import_module('app')
    app = app_mod.create_app('testing')
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI=test_database_url,
    )
    return app, app_mod.db


def _seed_admin_po(app, db, ordered_qty=10, product_stock=0):
    from app.auth.models import User, RoleEnum
    from app.inventory.models import Product
    from app.purchasing.models import Supplier, PurchaseOrder, PurchaseOrderItem, POStatus

    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(username='admin_p1', name='Admin P1', role=RoleEnum.admin)
        admin.set_password('admin-pass')
        db.session.add(admin)
        db.session.flush()

        supplier = Supplier(name='P1 Supplier')
        db.session.add(supplier)
        db.session.flush()

        product = Product(
            name='PO P1 Product',
            barcode=f'PO-P1-{ordered_qty}-{product_stock}',
            price=Decimal('100.00'),
            stock=product_stock,
            gst_percent=5,
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()

        po = PurchaseOrder(
            supplier_id=supplier.id,
            status=POStatus.SENT,
            created_by=admin.id,
        )
        db.session.add(po)
        db.session.flush()

        po_item = PurchaseOrderItem(
            po_id=po.id,
            product_id=product.id,
            ordered_qty=ordered_qty,
            unit_cost=Decimal('80.00'),
        )
        db.session.add(po_item)
        db.session.commit()
        return {
            'admin_id': admin.id,
            'supplier_id': supplier.id,
            'product_id': product.id,
            'po_id': po.id,
            'po_item_id': po_item.id,
        }


def _login(client):
    return client.post(
        '/auth/login',
        data={'username': 'admin_p1', 'password': 'admin-pass'},
        follow_redirects=True,
    )


def test_over_receipt_rejected(tmp_path):
    app, db = _make_app(tmp_path)
    ids = _seed_admin_po(app, db, ordered_qty=5, product_stock=2)

    with app.test_client() as client:
        _login(client)
        resp = client.post(
            f"/purchasing/{ids['po_id']}/receive",
            data={
                f"qty_{ids['po_item_id']}": '6',
                f"batch_{ids['po_item_id']}": 'LOT-OVER',
                f"expiry_{ids['po_item_id']}": str(date.today() + timedelta(days=30)),
            },
            follow_redirects=True,
        )
        body = resp.get_data(as_text=True)
        assert 'Over-receipt blocked' in body

    from app.inventory.models import Product
    from app.purchasing.models import GoodsReceipt, GoodsReceiptItem
    with app.app_context():
        product = db.session.get(Product, ids['product_id'])
        assert product.stock == 2
        assert GoodsReceipt.query.filter_by(po_id=ids['po_id']).count() == 0
        assert GoodsReceiptItem.query.count() == 0


def test_concurrent_grn_only_one_succeeds(tmp_path):
    app, db = _make_app(tmp_path)
    ids = _seed_admin_po(app, db, ordered_qty=10, product_stock=0)

    barrier = threading.Barrier(2)
    lock = threading.Lock()
    results = []

    def worker():
        with app.test_client() as client:
            _login(client)
            barrier.wait(timeout=5)
            resp = client.post(
                f"/purchasing/{ids['po_id']}/receive",
                data={
                    f"qty_{ids['po_item_id']}": '10',
                    f"batch_{ids['po_item_id']}": 'LOCK-LOT',
                    f"expiry_{ids['po_item_id']}": str(date.today() + timedelta(days=60)),
                },
                follow_redirects=True,
            )
            with lock:
                results.append(resp.get_data(as_text=True))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    from app.inventory.models import Product
    from app.purchasing.models import GoodsReceipt, GoodsReceiptItem
    with app.app_context():
        assert GoodsReceipt.query.filter_by(po_id=ids['po_id']).count() == 1
        assert sum(item.received_qty for item in GoodsReceiptItem.query.all()) == 10
        assert db.session.get(Product, ids['product_id']).stock == 10

    assert any('GRN #' in body for body in results)


def test_batch_upsert_atomic(tmp_path):
    app, db = _make_app(tmp_path)
    ids = _seed_admin_po(app, db, ordered_qty=10, product_stock=0)

    with app.test_client() as client:
        _login(client)
        r1 = client.post(
            f"/purchasing/{ids['po_id']}/receive",
            data={
                f"qty_{ids['po_item_id']}": '4',
                f"batch_{ids['po_item_id']}": 'LOT-UPSERT',
            },
            follow_redirects=True,
        )
        assert 'GRN #' in r1.get_data(as_text=True)

        r2 = client.post(
            f"/purchasing/{ids['po_id']}/receive",
            data={
                f"qty_{ids['po_item_id']}": '6',
                f"batch_{ids['po_item_id']}": 'LOT-UPSERT',
            },
            follow_redirects=True,
        )
        assert 'GRN #' in r2.get_data(as_text=True)

    from app.inventory.models import Product, ProductBatch, InventoryLog
    from app.purchasing.models import PurchaseOrder, POStatus
    with app.app_context():
        batches = ProductBatch.query.filter_by(
            product_id=ids['product_id'],
            batch_number='LOT-UPSERT',
        ).all()
        assert len(batches) == 1
        assert batches[0].quantity == 10
        assert db.session.get(Product, ids['product_id']).stock == 10

        po = db.session.get(PurchaseOrder, ids['po_id'])
        assert po.status == POStatus.RECEIVED

        logs = InventoryLog.query.filter_by(product_id=ids['product_id']).all()
        assert len(logs) == 2
        assert all(log.reason == 'PO_RECEIVE' for log in logs)
        assert all(log.reference == ids['po_id'] for log in logs)


def test_duplicate_batch_cleanup_before_unique_index(tmp_path):
    app, db = _make_app(tmp_path)
    ids = _seed_admin_po(app, db, ordered_qty=1, product_stock=0)

    from app.inventory.models import ProductBatch
    with app.app_context():
        db.session.add(ProductBatch(
            product_id=ids['product_id'],
            batch_number='DUP-1',
            quantity=3,
            expiry_date=date.today() + timedelta(days=10),
            cost_price=Decimal('50.00'),
        ))
        db.session.add(ProductBatch(
            product_id=ids['product_id'],
            batch_number='DUP-1',
            quantity=7,
            expiry_date=date.today() + timedelta(days=20),
            cost_price=Decimal('55.00'),
        ))
        db.session.commit()

    from cleanup_product_batch_duplicates import cleanup_duplicate_product_batches
    stats = cleanup_duplicate_product_batches(app)
    assert stats['merged_groups'] >= 1
    assert stats['deleted_rows'] >= 1

    with app.app_context():
        rows = ProductBatch.query.filter_by(
            product_id=ids['product_id'],
            batch_number='DUP-1',
        ).all()
        assert len(rows) == 1
        assert rows[0].quantity == 10
