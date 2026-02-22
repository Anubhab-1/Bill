import importlib
import os
import threading
from datetime import datetime as real_datetime
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


TEST_DATABASE_URL = _resolve_test_database_url()


def _make_app(tmp_path):
    if not TEST_DATABASE_URL.startswith('postgresql://'):
        raise RuntimeError('TEST_DATABASE_URL must start with postgresql://')
    os.environ['DATABASE_URL'] = TEST_DATABASE_URL

    app_mod = importlib.import_module('app')
    app = app_mod.create_app('testing')
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=TEST_DATABASE_URL,
    )
    return app, app_mod.db


def _patch_invoice_year(monkeypatch, year):
    import app.billing.invoice as invoice_mod

    class FixedDateTime:
        @classmethod
        def now(cls):
            return real_datetime(year, 1, 1, 9, 0, 0)

    monkeypatch.setattr(invoice_mod, 'datetime', FixedDateTime)


def test_first_invoice_of_year_concurrent(tmp_path, monkeypatch):
    app, db = _make_app(tmp_path)
    _patch_invoice_year(monkeypatch, 2027)

    with app.app_context():
        db.drop_all()
        db.create_all()

    results = []
    errors = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker():
        from app.billing.invoice import generate_invoice_number
        with app.app_context():
            try:
                barrier.wait(timeout=5)
                inv = generate_invoice_number(db.session)
                db.session.commit()
                with lock:
                    results.append(inv)
            except Exception as exc:
                db.session.rollback()
                with lock:
                    errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not any(type(e).__name__ == 'IntegrityError' for e in errors)
    assert not errors
    assert sorted(results) == ['2027-0001', '2027-0002']


def test_invoice_sequence_still_gap_free_on_rollback(tmp_path, monkeypatch):
    app, db = _make_app(tmp_path)
    _patch_invoice_year(monkeypatch, 2027)

    with app.app_context():
        db.drop_all()
        db.create_all()

        from app.billing.invoice import generate_invoice_number

        first = generate_invoice_number(db.session)
        assert first == '2027-0001'
        db.session.rollback()

        second = generate_invoice_number(db.session)
        db.session.commit()
        assert second == '2027-0001'
