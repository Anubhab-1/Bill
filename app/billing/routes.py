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
    clear_cart, cart_totals, update_cart_quantity,
    add_weighed_to_cart
)
from app.billing.invoice import generate_invoice_number
from app.inventory.models import Product, InventoryLog, ProductBatch
from app.customers.models import Customer, GiftCard
from app.billing.models import CashSession
from app.auth.decorators import login_required, admin_required
from app import db

# ── Promo engine (lazy import to avoid circular deps) ─────────────
def _get_promo_result(cart):
    try:
        from app.promotions.engine import evaluate_promotions
        from app.promotions.routes import get_active_promotions
        promos = get_active_promotions()
        return evaluate_promotions(cart, promos)
    except Exception:
        return None
from datetime import datetime

# ── HELPERS ───────────────────────────────────────────────────────

def get_stock_map(cart):
    """
    Fetch current stock levels for all products in the cart.
    Returns: { str(product_id): int(current_stock) }
    """
    if not cart:
        return {}
    
    # Get all product IDs from cart keys
    product_ids = [int(pid) for pid in cart.keys()]
    
    # Query DB for fresh stock levels
    products = Product.query.filter(Product.id.in_(product_ids)).all()
    
    return {str(p.id): p.stock for p in products}

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
    # Fetch stock levels for display/validation
    stock_map = get_stock_map(cart)

    customer = None
    if 'customer_id' in session:
        customer = db.session.get(Customer, session['customer_id'])

    return render_template(
        'billing/index.html',
        title='Billing',
        cart=cart,
        totals=totals,
        stock_map=stock_map,
        customer=customer,
    )


# ── ADD ITEM (HTMX) ───────────────────────────────────────────────

@billing.route('/add-item', methods=['POST'])
@login_required
def add_item():
    """
    HTMX endpoint: look up product by barcode, add to session cart.
    If the product is a weighed item, returns an HTMX OOB response that
    opens the weight-input modal instead of adding directly to cart.
    Returns the cart partial HTML so HTMX can swap it in-place.
    """
    barcode = request.form.get('barcode', '').strip()
    cart    = get_cart()
    error   = None

    if not barcode:
        error = 'Please enter a barcode.'
    else:
        product = Product.query.filter_by(barcode=barcode, is_active=True).first()

        if product is None:
            error = f'No product found for barcode "{barcode}".'
        elif product.stock <= 0:
            error = f'"{product.name}" is out of stock.'
        elif product.is_weighed:
            # Return HTMX OOB swap to open the weight modal
            from flask import jsonify
            totals    = cart_totals(cart)
            stock_map = get_stock_map(cart)
            cart_html = render_template(
                'billing/_cart.html',
                cart=cart, totals=totals, stock_map=stock_map, error=None
            )
            modal_html = render_template(
                'billing/_weight_modal.html',
                product=product
            )
            # Combine both via HTMX OOB — cart stays as is, modal opens
            return cart_html + modal_html
        else:
            current_qty = cart.get(str(product.id), {}).get('quantity', 0)
            if current_qty + 1 > product.stock:
                error = f'Insufficient stock for "{product.name}". Only {product.stock} available.'
            else:
                add_to_cart(product)
                cart = get_cart()

    totals       = cart_totals(cart)
    stock_map    = get_stock_map(cart)
    promo_result = _get_promo_result(cart)
    customer = db.session.get(Customer, session['customer_id']) if 'customer_id' in session else None

    return render_template(
        'billing/_cart.html',
        cart=cart,
        totals=totals,
        stock_map=stock_map,
        promo_result=promo_result,
        error=error,
        customer=customer,
    )


# ── ADD WEIGHED ITEM (HTMX) ───────────────────────────────────────

@billing.route('/add-weighed-item', methods=['POST'])
@login_required
def add_weighed_item():
    """
    HTMX: Accept weight input from the weight modal, add weighed item to cart.
    Also serves as the placeholder hook for serial/Bluetooth scale integration.
    """
    from decimal import Decimal, InvalidOperation
    product_id = request.form.get('product_id', '').strip()
    weight_str = request.form.get('weight_kg', '').strip()
    cart  = get_cart()
    error = None

    product = db.session.get(Product, int(product_id)) if product_id.isdigit() else None
    if product is None or not product.is_active:
        error = 'Product not found.'
    elif not product.is_weighed or not product.price_per_kg:
        error = 'Product is not a weighed item.'
    elif product.stock <= 0:
        error = f'"{product.name}" is out of stock.'
    else:
        try:
            weight_kg = Decimal(weight_str)
            if weight_kg <= 0:
                error = 'Weight must be greater than zero.'
        except (InvalidOperation, ValueError):
            error = 'Invalid weight — enter a number like 0.850'

        if not error:
            add_weighed_to_cart(product, weight_kg)
            cart = get_cart()

    totals       = cart_totals(cart)
    stock_map    = get_stock_map(cart)
    promo_result = _get_promo_result(cart)
    customer = db.session.get(Customer, session['customer_id']) if 'customer_id' in session else None
    
    return render_template(
        'billing/_cart.html',
        cart=cart, totals=totals, stock_map=stock_map,
        promo_result=promo_result, error=error, customer=customer
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

    cart         = get_cart()
    totals       = cart_totals(cart)
    stock_map    = get_stock_map(cart)
    promo_result = _get_promo_result(cart)
    customer = db.session.get(Customer, session['customer_id']) if 'customer_id' in session else None

    return render_template(
        'billing/_cart.html',
        cart=cart,
        totals=totals,
        stock_map=stock_map,
        promo_result=promo_result,
        error=None,
        customer=customer,
    )


@billing.route('/update-item', methods=['POST'])
def update_item():
    """
    HTMX: Increment/Decrement item quantity safely.
    Strictly checks DB stock before incrementing.
    """
    product_id = request.form.get('product_id', type=int)
    action     = request.form.get('action')  # 'incr' or 'decr'
    error      = None
    cart       = get_cart()

    if product_id and str(product_id) in cart:
        # Fetch fresh product to ensure stock check is real-time
        product = db.session.get(Product, product_id)
        
        if not product:
            error = "Product not found."
        else:
            current_qty = cart[str(product_id)]['quantity']
            
            if action == 'incr':
                # Check: (current + 1) vs Stock
                if current_qty + 1 > product.stock:
                    error = f"Limit reached. Only {product.stock} in stock."
                else:
                    update_cart_quantity(product_id, current_qty + 1)
            
            elif action == 'decr':
                update_cart_quantity(product_id, current_qty - 1)
    
    # Re-render cart with updated state
    cart         = get_cart()
    totals       = cart_totals(cart)
    stock_map    = get_stock_map(cart)
    promo_result = _get_promo_result(cart)
    customer = db.session.get(Customer, session['customer_id']) if 'customer_id' in session else None

    return render_template(
        'billing/_cart.html',
        cart=cart,
        totals=totals,
        stock_map=stock_map,
        promo_result=promo_result,
        error=error,
        customer=customer,
    )


# ── CUSTOMER MANAGEMENT ─────────────────────────────────────────

@billing.route('/customer/attach', methods=['POST'])
@login_required
def attach_customer():
    """Attach a customer to the current billing session."""
    customer_id = request.form.get('customer_id', type=int)
    if customer_id:
        customer = db.session.get(Customer, customer_id)
        if customer:
            session['customer_id'] = customer.id
            flash(f'Attached: {customer.name}', 'success')
        else:
            flash('Customer not found.', 'error')
    return redirect(url_for('billing.index'))

@billing.route('/customer/detach')
@login_required
def detach_customer():
    session.pop('customer_id', None)
    flash('Customer detached.', 'info')
    return redirect(url_for('billing.index'))


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
    customer_id = session.get('customer_id')

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
            product.stock -= qty   # deduct aggregate — still inside the locked transaction

            # ── FIFO batch deduction ───────────────────────────────────
            # Pull batches in FIFO order: earliest expiry first, NULLs last
            fifo_batches = (
                ProductBatch.query
                .filter_by(product_id=product.id)
                .filter(ProductBatch.quantity > 0)
                .order_by(
                    db.case((ProductBatch.expiry_date.is_(None), 1), else_=0),
                    ProductBatch.expiry_date.asc()
                )
                .with_for_update()
                .all()
            )
            remaining = qty
            for batch in fifo_batches:
                if remaining <= 0:
                    break
                take = min(batch.quantity, remaining)
                batch.quantity -= take
                remaining -= take

            if remaining > 0:
                # Batch records are behind product.stock (legacy data drift)
                current_app.logger.warning(
                    f"FIFO shortfall for product {product.id}: {remaining} units not covered by batches"
                )
            # ─────────────────────────────────────────────────────────

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
                weight_kg     = Decimal(item['weight_kg']) if item.get('weight_kg') else None,
                unit_label    = 'kg' if item.get('is_weighed') else None,
            ))

        # ── Evaluate & apply promotions ───────────────────────────
        promo_result = _get_promo_result(cart)
        discount     = Decimal('0')
        promo_applied_entries = []
        if promo_result and promo_result.total_discount > 0:
            discount = min(promo_result.total_discount, subtotal_total)
            subtotal_total -= discount
            promo_applied_entries = promo_result.applied

        # ── Generate invoice number (inside same transaction) ─────
        invoice_number = generate_invoice_number(db.session)

        # ── Persist Sale ──────────────────────────────────────────
        sale = Sale(
            invoice_number = invoice_number,
            cashier_id     = cashier_id,
            customer_id    = customer_id,
            total_amount   = subtotal_total,
            gst_total      = gst_total,
        )
        db.session.add(sale)
        
        # ── Process Payments ──────────────────────────────────────
        # Sum of line items is our definitive Total Revenue
        grand_total = subtotal_total + gst_total
        
        # Parse inputs
        try:
            p_cash    = Decimal(request.form.get('payment_cash') or '0')
            p_card    = Decimal(request.form.get('payment_card') or '0')
            p_upi     = Decimal(request.form.get('payment_upi') or '0') # renamed from 'other' or mapped to 'other'
            p_loyalty = Decimal(request.form.get('payment_loyalty') or '0')
            p_gift    = Decimal(request.form.get('payment_gift') or '0')
            gift_code = request.form.get('gift_card_code', '').strip()
            
            total_tendered = p_cash + p_card + p_upi + p_loyalty + p_gift
        except Exception:
            raise ValueError("Invalid payment amounts provided.")

        # Ensure full payment (allow tiny rounding error)
        if total_tendered < grand_total - Decimal('0.05'):
             # If completely empty (quick complete), default to Full Cash
             if total_tendered == 0:
                 p_cash = grand_total
             else:
                 raise ValueError(f"Insufficient payment. Paid: {total_tendered}, Total: {grand_total}")
        
        from app.billing.models import SalePayment
        
        # If Card/Other used, record them exactly
        # If Card/Other used, record them exactly
        if p_card > 0:
            db.session.add(SalePayment(sale=sale, payment_method='card', amount=p_card))
        if p_upi > 0:
            db.session.add(SalePayment(sale=sale, payment_method='upi', amount=p_upi))
            
        # ── Handle Loyalty Redemption ──
        if p_loyalty > 0:
             if not customer_id:
                 raise ValueError("Cannot redeem points without a customer attached.")
             
             customer_obj = db.session.get(Customer, customer_id)
             # Assumption: 1 Point = ₹1.00
             points_needed = int(p_loyalty) 
             if customer_obj.points < points_needed:
                 raise ValueError(f"Insufficient points. Has {customer_obj.points}, needs {points_needed}.")
             
             customer_obj.points -= points_needed
             db.session.add(SalePayment(sale=sale, payment_method='loyalty', amount=p_loyalty))
             
        # ── Handle Gift Card Redemption ──
        if p_gift > 0:
            if not gift_code:
                raise ValueError("Gift card code required.")
            gc = GiftCard.query.filter_by(code=gift_code, is_active=True).with_for_update().first()
            if not gc:
                 raise ValueError("Invalid gift card.")
            if gc.balance < p_gift:
                 raise ValueError(f"Insufficient gift card balance. Available: {gc.balance}")
            
            gc.balance -= p_gift
            db.session.add(SalePayment(sale=sale, payment_method='gift_card', amount=p_gift))

        # Determine Cash Revenue (Revenue = Total - NonCash)
        cash_revenue = grand_total - p_card - p_upi - p_loyalty - p_gift
        if cash_revenue > 0:
             db.session.add(SalePayment(sale=sale, payment_method='cash', amount=cash_revenue))

        # ── Accrue Loyalty Points ──
        if customer_id and grand_total > 0:
            # Rule: 1 Point per ₹100
             new_points = int(grand_total // 100)
             if new_points > 0:
                 customer_obj = db.session.get(Customer, customer_id) # Re-fetch or use existing
                 customer_obj.points += new_points

        
        # update current session total
        active_session = CashSession.query.filter(
            CashSession.cashier_id == cashier_id,
            CashSession.end_time == None
        ).first()
        
        if active_session:
             active_session.system_total += grand_total
             db.session.add(active_session)

        db.session.flush()   # assigns sale.id without committing

        for si in sale_items:
            si.sale_id = sale.id
            db.session.add(si)

        # ── Persist applied promotions ────────────────────────────
        from app.promotions.models import AppliedPromotion
        for entry in promo_applied_entries:
            ap = AppliedPromotion(
                sale_id         = sale.id,
                promotion_id    = entry.promo_id,
                promo_name      = entry.promo_name,
                discount_amount = entry.discount_amount,
                description     = entry.description,
            )
            db.session.add(ap)
            # Increment use counter
            if entry.promo_id:
                from app.promotions.models import Promotion
                promo_row = db.session.get(Promotion, entry.promo_id)
                if promo_row:
                    promo_row.current_uses += 1

        # ── Commit Sale ───────────────────────────────────────────
        db.session.commit()

        # ── Generate & Store Invoice Snapshot (HTML) ──────────────
        # We render the template now while data is fresh and hot.
        # This snapshot is saved to DB for historical accuracy.
        try:
            invoice_html = render_template(
                'billing/invoice.html',
                title=f'Invoice {sale.invoice_number}',
                sale=sale,
                reprint_mode=False
            )
            sale.print_html = invoice_html
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to save invoice snapshot: {e}")
            # Non-critical failure — sale is already committed.

        clear_cart()
        session.pop('customer_id', None) # Detach customer after sale
        
        current_app.logger.info(f"Sale completed by User ID {cashier_id}: {invoice_number} | Total: {sale.grand_total}")
        flash(f'Sale complete! Invoice {invoice_number}', 'success')
        return redirect(url_for('billing.invoice', sale_id=sale.id))

    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.error(f"Sale rollback (IntegrityError): {str(exc)}")
        flash('A database error occurred. Please try again.', 'error')
        return redirect(url_for('billing.index'))

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(f"Sale rollback (Unexpected Error): {exc}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('billing.index'))


# ── PRINTABLE INVOICE ─────────────────────────────────────────────

@billing.route('/invoice/<int:sale_id>')
@login_required
def invoice(sale_id):
    """Render a clean, printable invoice page (fresh render)."""
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        abort(404)

    return render_template(
        'billing/invoice.html',
        title=f'Invoice {sale.invoice_number}',
        sale=sale,
        reprint_mode=False,
    )


@billing.route('/reprint/<int:sale_id>')
@login_required
def reprint(sale_id):
    """
    Return the historical HTML snapshot of the invoice.
    Logged for security.
    """
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        abort(404)

    # Log reprint action
    current_app.logger.info(f"Invoice Reprint: User {session.get('user_id')} reprinted Sale {sale.id} ({sale.invoice_number})")

    if sale.print_html:
        return sale.print_html
    else:
        # Fallback for old sales without snapshot
        return render_template(
            'billing/invoice.html',
            title=f'Invoice {sale.invoice_number}',
            sale=sale,
            reprint_mode=True,
        )


# ── RETURNS & REFUNDS ─────────────────────────────────────────────

# ── PRINTING & QUEUE ──────────────────────────────────────────────

@billing.route('/mark-printed/<int:sale_id>', methods=['POST'])
@login_required
def mark_printed(sale_id):
    sale = db.session.get(Sale, sale_id)
    if sale:
        sale.is_printed = True
        db.session.commit()
        # Return empty string with 200 OK for safer HTMX swapping
        return '', 200
    return 'Sale not found', 404
        
@billing.route('/print-queue')
@login_required
def print_queue():
    """List sales from today that haven't been marked as printed."""
    # Filter: created_at >= last 7 days AND is_printed is False
    # This ensures pending prints don't disappear at midnight
    cutoff = today - timedelta(days=7)
    sales = Sale.query.filter(
        Sale.created_at >= cutoff,
        Sale.is_printed == False
    ).order_by(desc(Sale.created_at)).all()
    
    return render_template('billing/print_queue.html', sales=sales)


# ── RETURNS & REFUNDS ─────────────────────────────────────────────


from app.billing.models import Return, ReturnItem

@billing.route('/returns', methods=['GET', 'POST'])
@login_required
def returns_search():
    """Search for a sale to process a return."""
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        # Ensure exact match for invoice number
        sale = Sale.query.filter(Sale.invoice_number == query).first()
        
        if sale:
            return redirect(url_for('billing.returns_process', sale_id=sale.id))
        else:
            flash(f'Invoice "{query}" not found.', 'error')
    
    return render_template('billing/returns/search.html')


@billing.route('/returns/process/<int:sale_id>', methods=['GET', 'POST'])
@login_required
def returns_process(sale_id):
    """
    Process a return for a specific sale.
    GET: Show returnable items and quantities.
    POST: Process the return.
    """
    sale = db.session.get(Sale, sale_id)
    if not sale:
        flash('Sale not found.', 'error')
        return redirect(url_for('billing.returns_search'))

    # Calculate previously returned quantities per item
    # Map: sale_item_id -> total_returned_qty
    returned_map = {}
    for r in sale.returns:
        for ri in r.items:
            returned_map[ri.sale_item_id] = returned_map.get(ri.sale_item_id, 0) + ri.quantity

    if request.method == 'POST':
        try:
            current_app.logger.info(f"Processing return for Sale {sale.id} (Inv: {sale.invoice_number})")
            
            # Process the return
            refund_method = request.form.get('refund_method')
            note = request.form.get('note')
            
            if not refund_method:
                 raise ValueError("Refund method is required.")

            new_return = Return(
                sale_id=sale.id,
                processed_by=session['user_id'],
                refund_method=refund_method,
                total_refunded=0,
                note=note
            )
            
            total_refund = Decimal('0.00')
            items_returned = False

            for item in sale.items:
                # Get return qty from form for this item
                qty_str = request.form.get(f'qty_{item.id}')
                
                # Log what we received
                # current_app.logger.debug(f"Item {item.id}: Input qty='{qty_str}'")

                if not qty_str:
                    continue
                    
                try:
                    qty_to_return = int(qty_str)
                except ValueError:
                    continue
                    
                if qty_to_return <= 0:
                    continue

                # Validate against remaining quantity
                already_returned = returned_map.get(item.id, 0)
                remaining = item.quantity - already_returned
                
                if qty_to_return > remaining:
                    raise ValueError(f"Cannot return {qty_to_return} of {item.product.name}. Only {remaining} eligible.")

                # Create ReturnItem
                # Refund amount calculation: (Item Price + Tax) * Qty
                # Or simply item.subtotal_with_gst / item.quantity * qty_to_return
                # Better: item.price_at_sale * (1 + gst/100) * qty
                
                # Precise: Unit Price with Tax
                unit_refund = item.subtotal_with_gst / item.quantity
                line_refund = unit_refund * qty_to_return
                
                ri = ReturnItem(
                    sale_item_id=item.id,
                    product_id=item.product_id,
                    quantity=qty_to_return,
                    refund_amount=line_refund,
                    reason="Customer Return" # Can handle per-item reason later if needed
                )
                new_return.items.append(ri)
                total_refund += line_refund
                items_returned = True
                
                # ── Inventory Update ──
                product = db.session.get(Product, item.product_id)
                product.stock += qty_to_return
                
                # ── Log Inventory Change ──
                log = InventoryLog(
                    product_id=product.id,
                    old_stock=product.stock - qty_to_return,
                    new_stock=product.stock,
                    changed_by=session['user_id'],
                    reason=f"Return: Invoice {sale.invoice_number}"
                )
                db.session.add(log)

            if not items_returned:
                current_app.logger.warning(f"Return failed (No items selected) for {sale.invoice_number}")
                flash('No items selected for return. Please enter a quantity > 0.', 'warning')
                return redirect(url_for('billing.returns_process', sale_id=sale.id))

            new_return.total_refunded = total_refund
            db.session.add(new_return)
            db.session.commit()
            
            flash(f'Return processed successfully. Refund: ₹{total_refund:,.2f}', 'success')
            return redirect(url_for('billing.returns_process', sale_id=sale.id))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception(f"Return processing failed: {e}")
            flash('An unexpected error occurred.', 'error')
    
    return render_template(
        'billing/returns/process.html', 
        sale=sale,
        returned_map=returned_map
    )
