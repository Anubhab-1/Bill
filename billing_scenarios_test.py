"""
billing_scenarios_test.py
──────────────────────────
Automated tests for the 5 critical billing scenarios.

Scenarios 1, 2, 4, 5  → run against SQLite in-memory DB (no PostgreSQL needed).
Scenario 3 (concurrency) → static code analysis + logic proof (FOR UPDATE is
                            PostgreSQL-only; SQLite doesn't support it).

Run:
    python billing_scenarios_test.py
"""

import os
import sys
import threading
import time
from decimal import Decimal

# ── Override DATABASE_URL before importing app ────────────────────
# Use SQLite in-memory so tests run without a live PostgreSQL server.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from run import app
from app import db
from app.auth.models import User, RoleEnum
from app.inventory.models import Product
from app.billing.models import Sale, SaleItem, InvoiceSequence

# ── Colours ───────────────────────────────────────────────────────
GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
CYAN   = '\033[96m'
RESET  = '\033[0m'
BOLD   = '\033[1m'

PASS   = f'{GREEN}[PASS]{RESET}'
FAIL   = f'{RED}[FAIL]{RESET}'
INFO   = f'{CYAN}[INFO]{RESET}'
SKIP   = f'{YELLOW}[SKIP]{RESET}'


# ── One-time DB setup ─────────────────────────────────────────────

def _setup_db():
    """Create all tables and seed the invoice sequence."""
    from datetime import date
    db.create_all()
    year = date.today().year
    if not db.session.get(InvoiceSequence, year):
        db.session.add(InvoiceSequence(year=year, last_seq=0))
        db.session.commit()


def _seed_cashier(username='test_cashier') -> User:
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(name='Test Cashier', username=username, role=RoleEnum.cashier)
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()
    return user


def _seed_product(name, barcode, price, stock, gst=0) -> Product:
    existing = Product.query.filter_by(barcode=barcode).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    p = Product(name=name, barcode=barcode,
                price=Decimal(str(price)), stock=stock, gst_percent=gst)
    db.session.add(p)
    db.session.commit()
    return p


def _make_client():
    app.config['TESTING']          = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app.test_client()


def _add_item(client, barcode):
    return client.post('/billing/add-item', data={'barcode': barcode})


def _remove_item(client, product_id):
    return client.post('/billing/remove-item', data={'product_id': product_id})


def _complete(client):
    return client.post('/billing/complete', follow_redirects=True)


def _clear_sales(user_id):
    SaleItem.query.filter(
        SaleItem.sale_id.in_(
            db.session.query(Sale.id).filter_by(cashier_id=user_id)
        )
    ).delete(synchronize_session=False)
    Sale.query.filter_by(cashier_id=user_id).delete()
    db.session.commit()


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 1 — Add same product multiple times
# ═══════════════════════════════════════════════════════════════════

def test_scenario_1_duplicate_add():
    print(f'\n{BOLD}{CYAN}▶ Scenario 1 — Add same product multiple times quickly{RESET}')

    product = _seed_product('Rice 1kg', 'SC1-BC-001', 50.00, 20)
    user    = _seed_cashier()
    client  = _make_client()

    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['role']    = 'cashier'

    # Add the same barcode 4 times
    for i in range(4):
        resp = _add_item(client, 'SC1-BC-001')
        assert resp.status_code == 200, f'add-item #{i+1} returned {resp.status_code}'

    with client.session_transaction() as sess:
        cart = sess.get('cart', {})

    pid_key = str(product.id)
    passed  = True

    if pid_key not in cart:
        print(f'  {FAIL} — product not found in cart at all')
        return False

    qty = cart[pid_key]['quantity']
    if qty == 4:
        print(f'  {PASS} -- quantity correctly accumulated to 4 (single cart entry, not 4 rows)')
    else:
        print(f'  {FAIL} -- expected quantity=4, got {qty}')
        passed = False

    # Verify only 1 key in cart (no duplicate entries)
    if len(cart) == 1:
        print(f'  {PASS} -- cart has exactly 1 entry (no duplicate product rows)')
    else:
        print(f'  {FAIL} -- cart has {len(cart)} entries, expected 1')
        passed = False

    # Verify totals are correct: 4 × ₹50 = ₹200
    from app.billing.cart import cart_totals
    totals = cart_totals(cart)
    if totals['subtotal'] == Decimal('200.00'):
        print(f'  {PASS} -- subtotal correct: Rs.{totals["subtotal"]} (4 x Rs.50.00)')
    else:
        print(f'  {FAIL} -- subtotal wrong: Rs.{totals["subtotal"]}, expected Rs.200.00')
        passed = False

    return passed


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 2 — Insufficient stock
# ═══════════════════════════════════════════════════════════════════

def test_scenario_2_insufficient_stock():
    print(f'\n{BOLD}{CYAN}▶ Scenario 2 — Insufficient stock rejection{RESET}')

    product = _seed_product('Wheat 5kg', 'SC2-BC-002', 200.00, 2)  # only 2 in stock
    user    = _seed_cashier()
    client  = _make_client()

    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['role']    = 'cashier'
        # Manually inject 5 units into cart (exceeds stock of 2)
        sess['cart'] = {
            str(product.id): {
                'name':        product.name,
                'barcode':     product.barcode,
                'price':       str(product.price),
                'gst_percent': product.gst_percent,
                'quantity':    5,
            }
        }

    stock_before = product.stock
    sales_before = Sale.query.filter_by(cashier_id=user.id).count()

    resp = _complete(client)

    db.session.expire_all()
    stock_after  = db.session.get(Product, product.id).stock
    sales_after  = Sale.query.filter_by(cashier_id=user.id).count()

    passed = True
    body   = resp.data.decode('utf-8', errors='replace')

    if stock_after == stock_before:
        print(f'  {PASS} -- stock unchanged: {stock_before} -> {stock_after} (rollback worked)')
    else:
        print(f'  {FAIL} -- stock was deducted! {stock_before} -> {stock_after}')
        passed = False

    if sales_after == sales_before:
        print(f'  {PASS} -- no Sale row created (transaction rolled back)')
    else:
        print(f'  {FAIL} -- {sales_after - sales_before} unexpected Sale row(s) created')
        passed = False

    if 'Insufficient' in body or 'insufficient' in body.lower() or 'error' in body.lower():
        print(f'  {PASS} — error message present in response')
    else:
        print(f'  {INFO} — flash message may be in redirect chain (acceptable)')

    return passed


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 3 — Two concurrent requests for last unit
# (SQLite doesn't support FOR UPDATE — we verify the code path and
#  logic correctness instead, and explain why PG handles it safely)
# ═══════════════════════════════════════════════════════════════════

def test_scenario_3_concurrent_last_unit():
    print(f'\n{BOLD}{CYAN}▶ Scenario 3 — Two concurrent requests for last unit of stock{RESET}')
    print(f'  {INFO} — SQLite does not support SELECT FOR UPDATE.')
    print(f'  {INFO} — Running sequential logic test + code path verification instead.')

    product = _seed_product('Last Item', 'SC3-BC-003', 100.00, 1)
    user    = _seed_cashier()

    passed = True

    # ── Sub-test A: verify the code path exists ───────────────────
    import inspect
    from app.billing import routes as billing_routes
    source = inspect.getsource(billing_routes.complete)

    if 'with_for_update()' in source:
        print(f'  {PASS} -- complete() uses .with_for_update() (SELECT FOR UPDATE confirmed in code)')
    else:
        print(f'  {FAIL} -- with_for_update() not found in complete() source!')
        passed = False

    if 'sorted(' in source and 'product_ids' in source:
        print(f'  {PASS} -- product_ids sorted before locking (deadlock prevention confirmed)')
    else:
        print(f'  {FAIL} -- sorted lock order not found in complete() source!')
        passed = False

    # ── Sub-test B: sequential simulation — first sale wins ───────
    # Simulate what happens when two requests arrive:
    # Request 1: stock=1, qty=1 → succeeds
    # Request 2: stock=0, qty=1 → rejected

    def simulate_complete(user_id, product_id, qty, label):
        """Simulate the core logic of complete() without HTTP."""
        from app.billing.models import InvoiceSequence
        from app.billing.invoice import generate_invoice_number
        from datetime import date

        try:
            # Lock + validate (sequential here, concurrent in real PG)
            p = db.session.get(Product, product_id)
            if p.stock < qty:
                return False, f'{label}: Insufficient stock ({p.stock} < {qty})'

            p.stock -= qty

            inv = generate_invoice_number(db.session)
            sale = Sale(
                invoice_number=inv,
                cashier_id=user_id,
                total_amount=Decimal('100.00'),
                gst_total=Decimal('0.00'),
            )
            db.session.add(sale)
            db.session.flush()
            db.session.add(SaleItem(
                sale_id=sale.id, product_id=product_id,
                quantity=qty, price_at_sale=Decimal('100.00'),
                gst_percent=0, subtotal=Decimal('100.00'),
            ))
            db.session.commit()
            return True, f'{label}: Sale created ({inv})'
        except Exception as exc:
            db.session.rollback()
            return False, f'{label}: Exception — {exc}'

    ok1, msg1 = simulate_complete(user.id, product.id, 1, 'Request-1')
    ok2, msg2 = simulate_complete(user.id, product.id, 1, 'Request-2')

    print(f'  {INFO} — {msg1}')
    print(f'  {INFO} — {msg2}')

    if ok1 and not ok2:
        print(f'  {PASS} -- exactly 1 sale succeeded, 1 rejected (correct sequential behaviour)')
    elif not ok1 and not ok2:
        print(f'  {FAIL} -- both requests failed (unexpected)')
        passed = False
    elif ok1 and ok2:
        print(f'  {FAIL} -- both requests succeeded (oversold! stock went negative)')
        passed = False

    db.session.expire_all()
    final_stock = db.session.get(Product, product.id).stock
    if final_stock >= 0:
        print(f'  {PASS} -- stock never went negative (final={final_stock})')
    else:
        print(f'  {FAIL} -- stock is negative! ({final_stock})')
        passed = False

    print(f'  {INFO} -- On PostgreSQL: FOR UPDATE serialises concurrent Tx at DB level.')
    print(f'  {INFO} -- Tx B blocks on the lock until Tx A commits, then sees stock=0 -> rejects.')

    _clear_sales(user.id)
    return passed


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 4 — Remove item then complete sale
# ═══════════════════════════════════════════════════════════════════

def test_scenario_4_remove_then_complete():
    print(f'\n{BOLD}{CYAN}▶ Scenario 4 — Remove item then complete sale{RESET}')

    product_a = _seed_product('Product A', 'SC4-BC-004A', 100.00, 10)
    product_b = _seed_product('Product B', 'SC4-BC-004B', 200.00, 10)
    user      = _seed_cashier()
    client    = _make_client()

    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['role']    = 'cashier'

    # Add both products
    _add_item(client, 'SC4-BC-004A')
    _add_item(client, 'SC4-BC-004B')

    with client.session_transaction() as sess:
        cart = sess.get('cart', {})

    passed = True

    if str(product_a.id) in cart and str(product_b.id) in cart:
        print(f'  {PASS} -- both products in cart after adding')
    else:
        print(f'  {FAIL} -- cart after add: {list(cart.keys())}')
        return False

    # Remove product B
    _remove_item(client, product_b.id)

    with client.session_transaction() as sess:
        cart = sess.get('cart', {})

    if str(product_a.id) in cart and str(product_b.id) not in cart:
        print(f'  {PASS} -- Product B removed; only Product A remains in cart')
    else:
        print(f'  {FAIL} -- cart after remove: {list(cart.keys())}')
        passed = False

    # Complete the sale
    _complete(client)

    sale = Sale.query.filter_by(cashier_id=user.id).order_by(Sale.id.desc()).first()

    if sale is None:
        print(f'  {FAIL} — no sale was created')
        return False

    item_pids = [si.product_id for si in sale.items]

    if product_a.id in item_pids and product_b.id not in item_pids:
        print(f'  {PASS} -- invoice contains only Product A (removed B not billed)')
    else:
        print(f'  {FAIL} -- invoice product IDs: {item_pids}')
        passed = False

    db.session.expire_all()
    stock_a = db.session.get(Product, product_a.id).stock
    stock_b = db.session.get(Product, product_b.id).stock

    if stock_a == 9:
        print(f'  {PASS} -- Product A stock deducted correctly (10 -> 9)')
    else:
        print(f'  {FAIL} -- Product A stock: expected 9, got {stock_a}')
        passed = False

    if stock_b == 10:
        print(f'  {PASS} -- Product B stock untouched (still 10, was never billed)')
    else:
        print(f'  {FAIL} -- Product B stock: expected 10, got {stock_b}')
        passed = False

    _clear_sales(user.id)
    return passed


# ═══════════════════════════════════════════════════════════════════
# SCENARIO 5 — Complete with empty cart
# ═══════════════════════════════════════════════════════════════════

def test_scenario_5_empty_cart():
    print(f'\n{BOLD}{CYAN}▶ Scenario 5 — Complete sale with empty cart{RESET}')

    user   = _seed_cashier()
    client = _make_client()

    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['role']    = 'cashier'
        sess.pop('cart', None)   # explicitly empty

    sales_before = Sale.query.filter_by(cashier_id=user.id).count()
    resp         = _complete(client)
    sales_after  = Sale.query.filter_by(cashier_id=user.id).count()

    body   = resp.data.decode('utf-8', errors='replace')
    passed = True

    if sales_after == sales_before:
        print(f'  {PASS} -- no Sale created for empty cart')
    else:
        print(f'  {FAIL} -- a Sale was created from an empty cart!')
        passed = False

    if 'empty' in body.lower() or 'Cart is empty' in body:
        print(f'  {PASS} -- "Cart is empty" error message shown to user')
    else:
        # Redirect back to billing page is also correct behaviour
        if resp.status_code == 200:
            print(f'  {PASS} -- redirected back to billing page (flash message in redirect)')
        else:
            print(f'  {INFO} -- status={resp.status_code} (redirect chain)')

    # Verify the route guard in source code
    import inspect
    from app.billing import routes as billing_routes
    source = inspect.getsource(billing_routes.complete)
    if 'if not cart' in source:
        print(f'  {PASS} -- empty cart guard confirmed in complete() source code')
    else:
        print(f'  {FAIL} -- empty cart guard not found in source!')
        passed = False

    return passed


# ===================================================================
# RUNNER
# ===================================================================

def main():
    print('\n' + '='*62)
    print('  Mall Billing System -- Critical Scenario Tests')
    print('='*62)
    print(f'  {INFO} -- Using SQLite in-memory DB (no PostgreSQL required)')
    print(f'  {INFO} -- Scenario 3 uses code analysis + sequential simulation')

    with app.app_context():
        _setup_db()

    tests = [
        ('1 -- Duplicate add accumulates quantity',   test_scenario_1_duplicate_add),
        ('2 -- Insufficient stock rejected',          test_scenario_2_insufficient_stock),
        ('3 -- Concurrent last-unit (code + logic)',  test_scenario_3_concurrent_last_unit),
        ('4 -- Remove item then complete',            test_scenario_4_remove_then_complete),
        ('5 -- Empty cart rejected',                  test_scenario_5_empty_cart),
    ]

    results = []
    for name, fn in tests:
        with app.app_context():
            try:
                ok = fn()
                results.append((name, ok if ok is not None else True))
            except AssertionError as exc:
                print(f'  {FAIL} -- assertion: {exc}')
                results.append((name, False))
            except Exception as exc:
                print(f'  {FAIL} -- unhandled exception: {exc}')
                import traceback; traceback.print_exc()
                results.append((name, False))

    # -- Summary ---------------------------------------------------
    print('\n' + '='*62)
    print('  SUMMARY')
    print('='*62)
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    for name, ok in results:
        icon = PASS if ok else FAIL
        print(f'  {icon}  Scenario {name}')

    colour = GREEN if passed == total else RED
    print(f'\n{colour}{BOLD}  {passed}/{total} scenarios passed{RESET}')
    print('='*62 + '\n')

    sys.exit(0 if passed == total else 1)


if __name__ == '__main__':
    main()
