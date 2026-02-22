import importlib
import os
import sys
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

import pytest
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
        ALLOW_SCHEMA_FIX_ROUTE=False,
    )
    return app, app_mod.db


def _seed_admin_and_sale(app, db):
    from app.auth.models import RoleEnum, User
    from app.billing.models import CashSession, Sale, SaleItem
    from app.inventory.models import Product

    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(username='admin_p0', name='Admin P0', role=RoleEnum.admin)
        admin.set_password('admin-pass')
        db.session.add(admin)
        db.session.flush()

        active_session = CashSession(cashier_id=admin.id, opening_cash=Decimal('500.00'), system_total=0)
        db.session.add(active_session)

        product = Product(
            name='Race Test Product',
            barcode='RACE-001',
            price=Decimal('100.00'),
            stock=10,
            gst_percent=18,
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()

        sale = Sale(
            invoice_number='RACE-INV-001',
            cashier_id=admin.id,
            total_amount=Decimal('100.00'),
            gst_total=Decimal('18.00'),
            grand_total=Decimal('118.00'),
            is_printed=False,
            created_at=datetime.utcnow(),
        )
        db.session.add(sale)
        db.session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=1,
            price_at_sale=Decimal('100.00'),
            gst_percent=18,
            subtotal=Decimal('100.00'),
        )
        db.session.add(item)
        db.session.commit()
        return admin.id, sale.id, item.id


def _login(client):
    return client.post(
        '/auth/login',
        data={'username': 'admin_p0', 'password': 'admin-pass'},
        follow_redirects=True,
    )


def test_import_app_has_no_db_or_subprocess_side_effects(monkeypatch):
    import flask_sqlalchemy
    import subprocess

    called = {'create_all': 0, 'subprocess': 0}

    def _fail_create_all(*args, **kwargs):
        called['create_all'] += 1
        raise AssertionError('create_all must not run on package import')

    def _fail_subprocess(*args, **kwargs):
        called['subprocess'] += 1
        raise AssertionError('subprocess must not run on package import')

    monkeypatch.setattr(flask_sqlalchemy.SQLAlchemy, 'create_all', _fail_create_all, raising=True)
    monkeypatch.setattr(subprocess, 'run', _fail_subprocess, raising=True)

    sys.modules.pop('app', None)
    mod = importlib.import_module('app')
    assert hasattr(mod, 'create_app')
    assert not hasattr(mod, 'app')
    assert called['create_all'] == 0
    assert called['subprocess'] == 0


def test_create_app_has_no_migration_or_subprocess_side_effects(monkeypatch, tmp_path):
    import app.migration as migration_mod
    import subprocess

    called = {'migration': 0, 'subprocess': 0}

    def _mark_migration(*args, **kwargs):
        called['migration'] += 1

    def _mark_subprocess(*args, **kwargs):
        called['subprocess'] += 1
        raise AssertionError('subprocess must not run during create_app')

    monkeypatch.setattr(migration_mod, 'run_auto_migration', _mark_migration, raising=True)
    monkeypatch.setattr(subprocess, 'run', _mark_subprocess, raising=True)

    app, db = _make_app(tmp_path)
    with app.app_context():
        db.create_all()

    assert called['migration'] == 0
    assert called['subprocess'] == 0


def test_sale_grand_total_column_is_writable(tmp_path):
    app, db = _make_app(tmp_path)
    from app.auth.models import RoleEnum, User
    from app.billing.models import Sale

    with app.app_context():
        db.create_all()
        user = User(username='gt_user', name='GT User', role=RoleEnum.admin)
        user.set_password('pass')
        db.session.add(user)
        db.session.flush()

        sale = Sale(
            invoice_number='GT-001',
            cashier_id=user.id,
            total_amount=Decimal('100.00'),
            gst_total=Decimal('18.00'),
            grand_total=Decimal('118.00'),
        )
        db.session.add(sale)
        db.session.commit()

        stored = db.session.get(Sale, sale.id)
        assert Decimal(str(stored.grand_total)) == Decimal('118.00')
        assert stored.computed_grand_total == Decimal('118.00')


def test_update_item_requires_login(tmp_path):
    app, db = _make_app(tmp_path)
    with app.app_context():
        db.create_all()
    with app.test_client() as client:
        resp = client.post('/billing/update-item', data={'product_id': 1, 'action': 'incr'})
    assert resp.status_code in (301, 302)
    assert '/auth/login' in (resp.headers.get('Location') or '')


def test_fix_db_schema_route_disabled_by_flag(tmp_path, monkeypatch):
    app, db = _make_app(tmp_path)
    from app.auth.models import RoleEnum, User
    import app.migration as migration_mod

    with app.app_context():
        db.create_all()
        admin = User(username='admin_p0', name='Admin', role=RoleEnum.admin)
        admin.set_password('admin-pass')
        db.session.add(admin)
        db.session.commit()

    with app.test_client() as client:
        _login(client)
        resp = client.post('/fix-db-schema-now')
        assert resp.status_code == 404

        app.config['ALLOW_SCHEMA_FIX_ROUTE'] = True
        monkeypatch.setattr(migration_mod, 'run_auto_migration', lambda _app: None)
        resp = client.post('/fix-db-schema-now')
        assert resp.status_code == 200


def test_returns_concurrent_attempts_one_succeeds_one_fails(tmp_path):
    app, db = _make_app(tmp_path)
    _, sale_id, sale_item_id = _seed_admin_and_sale(app, db)

    c1 = app.test_client()
    c2 = app.test_client()
    _login(c1)
    _login(c2)

    r1 = c1.post(
        f'/billing/returns/process/{sale_id}',
        data={'refund_method': 'cash', f'qty_{sale_item_id}': '1'},
        follow_redirects=True,
    )
    b1 = r1.get_data(as_text=True)
    assert 'Return processed successfully' in b1

    r2 = c2.post(
        f'/billing/returns/process/{sale_id}',
        data={'refund_method': 'cash', f'qty_{sale_item_id}': '1'},
        follow_redirects=True,
    )
    b2 = r2.get_data(as_text=True)
    assert (
        'Cannot return' in b2
        or 'Another return is in progress' in b2
        or 'An unexpected error occurred.' in b2
    )

    from app.billing.models import Return, ReturnItem
    with app.app_context():
        total_returned = sum(ri.quantity for ri in ReturnItem.query.all())
        assert Return.query.count() == 1
        assert total_returned == 1


def test_health_and_print_queue_smoke(tmp_path):
    app, db = _make_app(tmp_path)
    _seed_admin_and_sale(app, db)

    with app.test_client() as client:
        _login(client)
        pq = client.get('/billing/print-queue')
        assert pq.status_code == 200

        hc = client.get('/health')
        assert hc.status_code in (200, 500)
        payload = hc.get_json()
        assert 'status' in payload
        assert 'details' in payload
        assert 'disk_free_percent' in payload['details']


def test_wsgi_import_loads(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'testing')
    sys.modules.pop('wsgi', None)
    mod = importlib.import_module('wsgi')
    assert hasattr(mod, 'app')


def test_logging_handlers_are_deduplicated(tmp_path):
    app, _ = _make_app(tmp_path)
    from app.utils.logging import setup_logging

    setup_logging(app)
    setup_logging(app)

    handler_names = [getattr(h, 'name', '') for h in app.logger.handlers]
    assert handler_names.count('mall_stream_handler') == 1
    assert handler_names.count('mall_file_handler') <= 1
