from decimal import Decimal
from flask import (
    render_template, redirect, url_for,
    request, flash, session, abort, current_app
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.billing import billing
from app.billing.models import Sale, SaleItem
from app.billing.cart import (
    get_cart, add_to_cart, remove_from_cart,
    clear_cart, cart_totals
)
from app.billing.invoice import generate_invoice_number
from app.inventory.models import Product, InventoryLog
from app.billing.models import CashSession
from app.auth.decorators import login_required, admin_required
from app import db
from datetime import datetime


# ── SESSION ENFORCEMENT ───────────────────────────────────────────

@billing.before_request
def enforce_session():
    """Ensure cashier has an open session before billing."""
    # Skip for static assets, auth, or if not logged in
    path = request.path
    if path.startswith('/static') or path.startswith('/auth'):
        return
    if not session.get('user_id'):
        return

    # Skip checking if we are already on session management/admin pages
    if request.view_args and 'session' in request.view_args: # No, path check better
        pass
    
    # Check explicitly allowed routes relative to 'billing'
    # request.endpoint example: 'billing.open_session'
    endpoint = request.endpoint
    if not endpoint or 'open_session' in endpoint or 'close_session' in endpoint or 'sessions' in endpoint:
        return

    # For billing actions (index, add/remove, complete), require active session
    if 'billing.' in endpoint:
        active = CashSession.query.filter(
            CashSession.cashier_id == session['user_id'],
            CashSession.end_time == None
        ).first()
        
        if not active:
            flash('Please open a cash session to start billing.', 'warning')
            return redirect(url_for('billing.open_session'))


# ── SESSION MANAGEMENT ────────────────────────────────────────────

@billing.route('/session/open', methods=['GET', 'POST'])
@login_required
def open_session():
    active = CashSession.query.filter(
        CashSession.cashier_id == session['user_id'],
        CashSession.end_time == None
    ).first()
    
    if active:
        return redirect(url_for('billing.index'))
        
    if request.method == 'POST':
        try:
            opening = Decimal(request.form['opening_cash'])
            new_session = CashSession(
                cashier_id=session['user_id'],
                opening_cash=opening,
                system_total=0
            )
            db.session.add(new_session)
            db.session.commit()
            flash('Cash session opened.', 'success')
            return redirect(url_for('billing.index'))
        except Exception as e:
            flash(f'Error opening session: {e}', 'error')
            
    return render_template('billing/open_session.html')


@billing.route('/session/close', methods=['GET', 'POST'])
@login_required
def close_session():
    active = CashSession.query.filter(
        CashSession.cashier_id == session['user_id'],
        CashSession.end_time == None
    ).first()
    
    if not active:
        flash('No active session found.', 'warning')
        return redirect(url_for('billing.index'))
        
    if request.method == 'POST':
        try:
            closing = Decimal(request.form['closing_cash'])
            active.closing_cash = closing
            active.end_time = datetime.utcnow()
            
            # Flush to calculate discrepancy property
            db.session.flush()
            diff = active.discrepancy
            
            if diff != 0:
                current_app.logger.warning(
                    f"Session Closed (ID {active.id}): Discrepancy {diff} "
                    f"(Exp: {active.opening_cash + active.system_total}, Act: {closing})"
                )
            
            db.session.commit()
            flash(f'Session closed. Discrepancy: ₹{diff}', 'info')
            return redirect(url_for('main.index'))
        except Exception as e:
            flash(f'Error closing session: {e}', 'error')
            
    return render_template('billing/close_session.html', session=active)


@billing.route('/sessions')
@admin_required
def sessions():
    """Admin view of session history."""
    history = CashSession.query.order_by(CashSession.start_time.desc()).all()
    return render_template('billing/sessions.html', sessions=history)


# ── BILLING SCREEN ────────────────────────────────────────────────

@billing.route('/')
@login_required
def index():
    """Main billing screen — barcode input + live cart."""
    cart   = get_cart()
    totals = cart_totals(cart)
    return render_template(
        'billing/index.html',
        title='Billing',
        cart=cart,
        totals=totals,
    )


# ── ADD ITEM (HTMX) ───────────────────────────────────────────────

@billing.route('/add-item', methods=['POST'])
@login_required
def add_item():
    """
    HTMX endpoint: look up product by barcode, add to session cart.
    Returns the cart partial HTML so HTMX can swap it in-place.
    """
    barcode = request.form.get('barcode', '').strip()
    error   = None

    if not barcode:
        error = 'Please enter a barcode.'
    else:
        product = Product.query.filter_by(barcode=barcode, is_active=True).first()
        if product is None:
            error = f'No product found for barcode "{barcode}".'
        elif product.stock <= 0:
            error = f'"{product.name}" is out of stock.'
        else:
            add_to_cart(product)

    cart   = get_cart()
    totals = cart_totals(cart)

    return render_template(
        'billing/_cart.html',
        cart=cart,
        totals=totals,
        error=error,
    )


# ── REMOVE ITEM (HTMX) ───────────────────────────────────────────

@billing.route('/remove-item', methods=['POST'])
@login_required
def remove_item():
    """
    HTMX endpoint: remove a product from the session cart.
    Returns the cart partial HTML.
    """
    product_id = request.form.get('product_id', type=int)
    if product_id:
        remove_from_cart(product_id)

    cart   = get_cart()
    totals = cart_totals(cart)

    return render_template(
        'billing/_cart.html',
        cart=cart,
        totals=totals,
        error=None,
    )


# ── COMPLETE SALE ─────────────────────────────────────────────────

@billing.route('/complete', methods=['POST'])
@login_required
def complete():
    """
    Finalise the sale:
      1. Lock each product row with SELECT … FOR UPDATE
      2. Verify stock is sufficient for every item
      3. Deduct stock
      4. Generate invoice number
      5. Persist Sale + SaleItems
      6. Commit
      7. Clear cart
      8. Redirect to printable invoice
    """
    cart = get_cart()

    if not cart:
        flash('Cart is empty. Add products before completing a sale.', 'error')
        return redirect(url_for('billing.index'))

    cashier_id = session.get('user_id')

    try:
        # ── Lock all product rows in a deterministic order ────────
        # Sorting by product_id prevents deadlocks when two concurrent
        # transactions try to lock the same rows in different orders.
        product_ids = sorted(int(pid) for pid in cart.keys())

        locked_products = {}
        for pid in product_ids:
            # SELECT … FOR UPDATE — holds a row-level lock until COMMIT/ROLLBACK
            product = (
                db.session.query(Product)
                .filter(Product.id == pid)
                .with_for_update()
                .first()
            )
            if product is None:
                raise ValueError(f'Product ID {pid} no longer exists.')
            locked_products[str(pid)] = product

        # ── Stock validation (all-or-nothing) ─────────────────────
        for pid_str, item in cart.items():
            product  = locked_products[pid_str]
            required = item['quantity']
            if product.stock < required:
                raise ValueError(
                    f'Insufficient stock for "{product.name}". '
                    f'Available: {product.stock}, requested: {required}.'
                )

        # ── Deduct stock + build line items ───────────────────────
        subtotal_total = Decimal('0')
        gst_total      = Decimal('0')
        sale_items     = []

        for pid_str, item in cart.items():
            product  = locked_products[pid_str]
            qty      = item['quantity']
            price    = Decimal(item['price'])
            gst_rate = Decimal(item['gst_percent']) / Decimal('100')

            line_subtotal = (price * qty).quantize(Decimal('0.01'))
            line_gst      = (line_subtotal * gst_rate).quantize(Decimal('0.01'))

            old_stock = product.stock
            product.stock -= qty   # deduct — still inside the locked transaction
            
            # Log stock change
            log = InventoryLog(
                product_id=product.id,
                old_stock=old_stock,
                new_stock=product.stock,
                changed_by=cashier_id,
                reason="Sale Deduction"
            )
            db.session.add(log)

            subtotal_total += line_subtotal
            gst_total      += line_gst

            sale_items.append(SaleItem(
                product_id    = int(pid_str),
                quantity      = qty,
                price_at_sale = price,
                gst_percent   = item['gst_percent'],
                subtotal      = line_subtotal,
            ))

        # ── Generate invoice number (inside same transaction) ─────
        invoice_number = generate_invoice_number(db.session)

        # ── Persist Sale ──────────────────────────────────────────
        sale = Sale(
            invoice_number = invoice_number,
            cashier_id     = cashier_id,
            total_amount   = subtotal_total,
            gst_total      = gst_total,
        )
        db.session.add(sale)
        
        # update current session total
        # (Already enforced existance by before_request, but verify to be safe)
        active_session = CashSession.query.filter(
            CashSession.cashier_id == cashier_id,
            CashSession.end_time == None
        ).first()
        
        if active_session:
             # sale.grand_total is a property computed from instance state
             # We can use subtotal_total + gst_total
             active_session.system_total += (subtotal_total + gst_total)
             db.session.add(active_session)

        db.session.flush()   # assigns sale.id without committing

        for si in sale_items:
            si.sale_id = sale.id
            db.session.add(si)

        db.session.commit()
        clear_cart()
        
        current_app.logger.info(f"Sale completed by User ID {cashier_id}: {invoice_number} | Total: {sale.grand_total}")
        flash(f'Sale complete! Invoice {invoice_number}', 'success')
        return redirect(url_for('billing.invoice', sale_id=sale.id))

    except ValueError as exc:
        db.session.rollback()
        current_app.logger.warning(f"Sale rollback (ValueError): {str(exc)}")
        flash(str(exc), 'error')
        return redirect(url_for('billing.index'))

    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.error(f"Sale rollback (IntegrityError): {str(exc)}")
        flash('A database error occurred. Please try again.', 'error')
        return redirect(url_for('billing.index'))


# ── PRINTABLE INVOICE ─────────────────────────────────────────────

@billing.route('/invoice/<int:sale_id>')
@login_required
def invoice(sale_id):
    """Render a clean, printable invoice page."""
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        abort(404)

    return render_template(
        'billing/invoice.html',
        title=f'Invoice {sale.invoice_number}',
        sale=sale,
    )
