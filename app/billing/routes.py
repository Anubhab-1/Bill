from decimal import Decimal, ROUND_HALF_UP
from flask import (
    render_template, redirect, url_for,
    request, flash, session, abort, current_app
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.billing import billing
from app.billing.models import Return, ReturnItem, Sale, SaleItem, SalePayment
from app.billing.cart import (
    get_cart, add_to_cart, remove_from_cart,
    clear_cart, cart_totals, update_cart_quantity,
    add_weighed_to_cart
)
from app.billing.invoice import generate_invoice_number
from app.inventory.models import InventoryLog, ProductVariant
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
from datetime import datetime, timedelta

# ── HELPERS ───────────────────────────────────────────────────────

def get_stock_map(cart):
    """
    Fetch current stock levels for all variants in the cart.
    Returns: { str(variant_id): int(current_stock) }
    """
    if not cart:
        return {}
    
    variant_ids = [int(vid) for vid in cart.keys()]
    variants = ProductVariant.query.filter(ProductVariant.id.in_(variant_ids)).all()
    return {str(v.id): v.stock for v in variants}


def _build_returned_map(sale_obj):
    returned = {}
    for ret in sale_obj.returns:
        for ret_item in ret.items:
            returned[ret_item.sale_item_id] = returned.get(ret_item.sale_item_id, 0) + ret_item.quantity
    return returned

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
            db.session.rollback()
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
            db.session.rollback()
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
    promo_result = _get_promo_result(cart)

    customer = None
    if 'customer_id' in session:
        customer = db.session.get(Customer, session['customer_id'])

    return render_template(
        'billing/index.html',
        title='Billing',
        cart=cart,
        totals=totals,
        stock_map=stock_map,
        promo_result=promo_result,
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
        variant = ProductVariant.query.filter_by(barcode=barcode, is_active=True).first()
        product = variant.product if variant else None

        if variant is None or product is None or not product.is_active:
            error = f'No product found for barcode "{barcode}".'
        elif variant.stock <= 0:
            error = f'"{product.name}" is out of stock.'
        elif product.is_weighed:
            # Return HTMX OOB swap to open the weight modal
            totals    = cart_totals(cart)
            stock_map = get_stock_map(cart)
            cart_html = render_template(
                'billing/_cart.html',
                cart=cart, totals=totals, stock_map=stock_map, error=None
            )
            modal_html = render_template(
                'billing/_weight_modal.html',
                product=product,
                variant=variant,
            )
            # Combine both via HTMX OOB — cart stays as is, modal opens
            return cart_html + modal_html
        else:
            current_qty = cart.get(str(variant.id), {}).get('quantity', 0)
            if current_qty + 1 > variant.stock:
                error = f'Insufficient stock for "{product.name}". Only {variant.stock} available.'
            else:
                add_to_cart(variant)
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
    variant_id = (request.form.get('variant_id') or request.form.get('product_id') or '').strip()
    weight_str = request.form.get('weight_kg', '').strip()
    cart  = get_cart()
    error = None

    variant = db.session.get(ProductVariant, int(variant_id)) if variant_id.isdigit() else None
    product = variant.product if variant else None
    if variant is None or product is None or not variant.is_active or not product.is_active:
        error = 'Product not found.'
    elif not product.is_weighed or not product.price_per_kg:
        error = 'Product is not a weighed item.'
    elif variant.stock <= 0:
        error = f'"{product.name}" is out of stock.'
    else:
        try:
            weight_kg = Decimal(weight_str)
            if weight_kg <= 0:
                error = 'Weight must be greater than zero.'
        except (InvalidOperation, ValueError):
            error = 'Invalid weight — enter a number like 0.850'

        if not error:
            add_weighed_to_cart(variant, weight_kg)
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
    variant_id = request.form.get('variant_id', type=int)
    if variant_id is None:
        variant_id = request.form.get('product_id', type=int)
    if variant_id:
        remove_from_cart(variant_id)

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
@login_required
def update_item():
    """
    HTMX: Increment/Decrement item quantity safely.
    Strictly checks DB stock before incrementing.
    """
    variant_id = request.form.get('variant_id', type=int)
    if variant_id is None:
        variant_id = request.form.get('product_id', type=int)
    action     = request.form.get('action')  # 'incr' or 'decr'
    error      = None
    cart       = get_cart()

    if variant_id and str(variant_id) in cart:
        # Fetch fresh variant to ensure stock check is real-time
        variant = db.session.get(ProductVariant, variant_id)
        
        if not variant:
            error = "Product not found."
        else:
            current_qty = cart[str(variant_id)]['quantity']
            
            if action == 'incr':
                # Check: (current + 1) vs Stock
                if current_qty + 1 > variant.stock:
                    error = f"Limit reached. Only {variant.stock} in stock."
                else:
                    update_cart_quantity(variant_id, current_qty + 1)
            
            elif action == 'decr':
                update_cart_quantity(variant_id, current_qty - 1)
    
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


@billing.route('/new-sale', methods=['POST'])
@login_required
def new_sale():
    """HTMX endpoint to clear the cart and start a new sale."""
    clear_cart()
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
      1. Lock each variant row with SELECT … FOR UPDATE
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
        # ── Lock all variant rows in a deterministic order ────────
        # Sorting by variant_id prevents deadlocks when two concurrent
        # transactions try to lock the same rows in different orders.
        variant_ids = sorted(int(pid) for pid in cart.keys())

        locked_variants = {}
        for vid in variant_ids:
            # SELECT … FOR UPDATE — holds a row-level lock until COMMIT/ROLLBACK
            variant = (
                db.session.query(ProductVariant)
                .filter(ProductVariant.id == vid)
                .with_for_update()
                .first()
            )
            if variant is None or variant.product is None or not variant.product.is_active:
                raise ValueError(f'Variant ID {vid} no longer exists.')
            locked_variants[str(vid)] = variant

        # ── Stock validation (all-or-nothing) ─────────────────────
        for pid_str, item in cart.items():
            variant  = locked_variants[pid_str]
            required = item['quantity']
            if variant.stock < required:
                raise ValueError(
                    f'Insufficient stock for "{variant.product.name}". '
                    f'Available: {variant.stock}, requested: {required}.'
                )


        subtotal_before_discount = Decimal('0.00')
        line_items = []

        for pid_str, item in cart.items():
            variant = locked_variants[pid_str]
            qty = item['quantity']
            price = Decimal(item['price'])
            gst_rate = Decimal(item['gst_percent']) / Decimal('100')

            line_subtotal_base = (price * qty).quantize(Decimal('0.01'))
            variant.stock -= qty

            subtotal_before_discount += line_subtotal_base
            line_items.append({
                'variant': variant,
                'qty': qty,
                'price': price,
                'gst_percent': int(item['gst_percent']),
                'gst_rate': gst_rate,
                'line_subtotal_base': line_subtotal_base,
                'weight_kg': Decimal(item['weight_kg']) if item.get('weight_kg') else None,
                'unit_label': 'kg' if item.get('is_weighed') else None,
            })

        promo_result = _get_promo_result(cart)
        promo_discount = Decimal('0.00')
        promo_applied_entries = []
        if promo_result and promo_result.total_discount > 0:
            promo_discount = min(
                Decimal(str(promo_result.total_discount)),
                subtotal_before_discount,
            ).quantize(Decimal('0.01'))
            promo_applied_entries = promo_result.applied

        discount_type = (request.form.get('discount_type') or '').strip().lower()
        discount_value_raw = (request.form.get('discount_value') or '').strip()
        manual_discount_percent = Decimal('0.00')
        manual_discount_amount = Decimal('0.00')
        if discount_value_raw:
            try:
                discount_value = Decimal(discount_value_raw)
            except Exception:
                raise ValueError("Invalid discount value.")
            if discount_value < 0:
                raise ValueError("Discount cannot be negative.")
            if discount_type == 'percent':
                if discount_value > 100:
                    raise ValueError("Discount percent cannot exceed 100.")
                manual_discount_percent = discount_value.quantize(Decimal('0.01'))
                manual_discount_amount = (
                    subtotal_before_discount * manual_discount_percent / Decimal('100')
                ).quantize(Decimal('0.01'))
            elif discount_type == 'amount':
                manual_discount_amount = discount_value.quantize(Decimal('0.01'))
            else:
                raise ValueError("Invalid discount type selected.")

        max_manual_allowed = (subtotal_before_discount - promo_discount).quantize(Decimal('0.01'))
        if max_manual_allowed < 0:
            max_manual_allowed = Decimal('0.00')
        if manual_discount_amount > max_manual_allowed:
            raise ValueError("Discount cannot exceed subtotal.")

        total_discount_amount = (promo_discount + manual_discount_amount).quantize(Decimal('0.01'))
        subtotal_total = (subtotal_before_discount - total_discount_amount).quantize(Decimal('0.01'))
        if subtotal_total < 0:
            raise ValueError("Discount cannot exceed subtotal.")

        if subtotal_before_discount > 0 and subtotal_total < subtotal_before_discount:
            discount_factor = subtotal_total / subtotal_before_discount
            for line in line_items:
                line['discounted_subtotal'] = (
                    line['line_subtotal_base'] * discount_factor
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            allocated = sum(line['discounted_subtotal'] for line in line_items)
            delta = subtotal_total - allocated
            if delta != 0 and line_items:
                target_line = max(line_items, key=lambda x: x['discounted_subtotal'])
                adjusted = target_line['discounted_subtotal'] + delta
                if adjusted < 0:
                    raise ValueError("Discount allocation failed.")
                target_line['discounted_subtotal'] = adjusted.quantize(Decimal('0.01'))
        else:
            for line in line_items:
                line['discounted_subtotal'] = line['line_subtotal_base']

        gst_total = Decimal('0.00')
        sale_items = []
        for line in line_items:
            line_gst = (
                line['discounted_subtotal'] * line['gst_rate']
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            gst_total += line_gst

            sale_items.append(SaleItem(
                variant_id=int(line['variant'].id),
                quantity=line['qty'],
                price_at_sale=line['price'],
                snapshot_size=line['variant'].size,
                snapshot_color=line['variant'].color,
                gst_percent=line['gst_percent'],
                subtotal=line['discounted_subtotal'],
                weight_kg=line['weight_kg'],
                unit_label=line['unit_label'],
            ))

        invoice_number = generate_invoice_number(db.session)

        grand_total = subtotal_total + gst_total
        # ── Persist Sale ──────────────────────────────────────────
        total_discount_amount = (promo_discount + manual_discount_amount).quantize(Decimal('0.01'))
        
        sale = Sale(
            invoice_number=invoice_number,
            cashier_id=cashier_id,
            customer_id=customer_id,
            total_amount=subtotal_total,
            discount_percent=manual_discount_percent,
            discount_amount=total_discount_amount,  # Persist TOTAL discount (promo + manual)
            gst_total=gst_total,
            grand_total=grand_total,
        )
        db.session.add(sale)
        db.session.flush() # Ensure sale.id is available
        
        # ── Process Payments ──────────────────────────────────────
        # Sum of line items is our definitive Total Revenue
        
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
        
        # Build JSON receipt payload for hardware agent
        receipt_data = {
            'invoice_number': sale.invoice_number,
            'subtotal': float(sale.total_amount),
            'gst_total': float(sale.gst_total),
            'grand_total': float(sale.grand_total),
            'items': [
                {
                    'name': item.product.name if item.product else 'Unknown',
                    'qty': item.quantity,
                    'price': float(item.unit_price),
                    'subtotal': float(item.subtotal)
                } for item in sale.items
            ]
        }

        if request.headers.get('Accept') == 'application/json':
            return jsonify({
                'status': 'success',
                'redirect': url_for('billing.invoice', sale_id=sale.id),
                'receipt': receipt_data
            })

        flash(f'Sale complete! Invoice {invoice_number}', 'success')
        return redirect(url_for('billing.invoice', sale_id=sale.id))

    except ValueError as exc:
        db.session.rollback()
        current_app.logger.error(f"Sale rollback (ValueError): {str(exc)}")
        flash(str(exc), 'error')
        return redirect(url_for('billing.index'))

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
    cutoff = datetime.utcnow() - timedelta(days=7)
    sales = Sale.query.filter(
        Sale.created_at >= cutoff,
        Sale.is_printed == False
    ).order_by(Sale.created_at.desc()).all()
    
    return render_template('billing/print_queue.html', sales=sales)


@billing.route('/exchange/<int:sale_id>', methods=['GET', 'POST'])
@login_required
def exchange_process(sale_id):
    """
    Exchange one previously sold line for another active variant.
    Stock movement is atomic:
      - old sold variant stock += qty
      - new variant stock -= qty
    """
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        flash('Sale not found.', 'error')
        return redirect(url_for('billing.returns_search'))

    returned_map = _build_returned_map(sale)
    returnable_items = []
    for item in sale.items:
        already_returned = returned_map.get(item.id, 0)
        remaining = item.quantity - already_returned
        if remaining <= 0:
            continue
        if item.variant is None:
            continue
        unit_total = (
            item.subtotal_with_gst / Decimal(item.quantity)
        ).quantize(Decimal('0.01'))
        returnable_items.append({
            'item': item,
            'remaining': remaining,
            'unit_total': unit_total,
        })

    new_variants_raw = (
        ProductVariant.query
        .filter(
            ProductVariant.is_active.is_(True),
            ProductVariant.product.has(is_active=True),
        )
        .order_by(ProductVariant.product_id.asc(), ProductVariant.size.asc(), ProductVariant.color.asc())
        .all()
    )
    new_variants = []
    for variant in new_variants_raw:
        gst_rate = Decimal(variant.product.gst_percent) / Decimal('100')
        unit_total = (Decimal(str(variant.price)) * (Decimal('1') + gst_rate)).quantize(Decimal('0.01'))
        new_variants.append({
            'variant': variant,
            'unit_total': unit_total,
            'gst_percent': variant.product.gst_percent,
        })

    if request.method == 'POST':
        try:
            sale_item_id = request.form.get('sale_item_id', type=int)
            new_variant_id = request.form.get('new_variant_id', type=int)
            qty = request.form.get('quantity', type=int)
            collect_method = (request.form.get('collect_method') or 'cash').strip().lower()
            refund_method = (request.form.get('refund_method') or 'cash').strip().lower()
            note = (request.form.get('note') or '').strip()

            if sale_item_id is None or new_variant_id is None or qty is None:
                raise ValueError('Old item, new variant, and quantity are required.')
            if qty <= 0:
                raise ValueError('Quantity must be greater than zero.')

            if collect_method not in {'cash', 'card', 'upi'}:
                collect_method = 'cash'
            if refund_method not in {'cash', 'card', 'upi', 'store_credit'}:
                refund_method = 'cash'

            sale_locked = (
                db.session.query(Sale)
                .filter(Sale.id == sale_id)
                .with_for_update()
                .first()
            )
            if sale_locked is None:
                raise ValueError('Sale not found.')

            sale_item_locked = (
                db.session.query(SaleItem)
                .filter(
                    SaleItem.id == sale_item_id,
                    SaleItem.sale_id == sale_locked.id,
                )
                .with_for_update()
                .first()
            )
            if sale_item_locked is None:
                raise ValueError('Selected sold item is invalid.')

            existing_return_items = (
                db.session.query(ReturnItem)
                .join(Return, ReturnItem.return_id == Return.id)
                .filter(Return.sale_id == sale_locked.id)
                .with_for_update()
                .all()
            )
            returned_map_tx = {}
            for ret_item in existing_return_items:
                returned_map_tx[ret_item.sale_item_id] = returned_map_tx.get(ret_item.sale_item_id, 0) + ret_item.quantity

            already_returned = returned_map_tx.get(sale_item_locked.id, 0)
            remaining = sale_item_locked.quantity - already_returned
            if qty > remaining:
                raise ValueError(
                    f'Cannot exchange {qty}. Only {remaining} item(s) remain eligible on this invoice.'
                )

            old_variant_id = sale_item_locked.variant_id
            if old_variant_id is None:
                raise ValueError('Original variant not found on selected sale item.')
            if old_variant_id == new_variant_id:
                raise ValueError('Please select a different replacement variant.')

            # Lock both variant rows in deterministic order to prevent deadlocks.
            locked_variants = {}
            for vid in sorted({old_variant_id, new_variant_id}):
                variant = (
                    db.session.query(ProductVariant)
                    .filter(ProductVariant.id == vid)
                    .with_for_update()
                    .first()
                )
                if variant is None:
                    raise ValueError(f'Variant {vid} no longer exists.')
                locked_variants[vid] = variant

            old_variant = locked_variants[old_variant_id]
            new_variant = locked_variants[new_variant_id]

            if new_variant.product is None or not new_variant.product.is_active or not new_variant.is_active:
                raise ValueError('Selected replacement variant is inactive.')
            if new_variant.stock < qty:
                raise ValueError(
                    f'Insufficient stock for replacement variant. Available: {new_variant.stock}.'
                )

            old_line_total = (
                sale_item_locked.subtotal_with_gst * Decimal(qty) / Decimal(sale_item_locked.quantity)
            ).quantize(Decimal('0.01'))

            new_unit_price = Decimal(str(new_variant.price))
            new_gst_percent = int(new_variant.product.gst_percent)
            new_line_subtotal = (new_unit_price * Decimal(qty)).quantize(Decimal('0.01'))
            new_line_gst = (
                new_line_subtotal * Decimal(new_gst_percent) / Decimal('100')
            ).quantize(Decimal('0.01'))
            new_line_total = (new_line_subtotal + new_line_gst).quantize(Decimal('0.01'))

            difference = (new_line_total - old_line_total).quantize(Decimal('0.01'))
            refund_amount = (Decimal('0.00') - difference).quantize(Decimal('0.01')) if difference < 0 else Decimal('0.00')

            product_by_id = {}
            for variant in (old_variant, new_variant):
                if variant.product_id not in product_by_id:
                    product_by_id[variant.product_id] = variant.product
            stock_before = {
                pid: product.total_stock
                for pid, product in product_by_id.items()
            }

            old_variant.stock += qty
            new_variant.stock -= qty

            stock_after = {
                pid: product.total_stock
                for pid, product in product_by_id.items()
            }

            exchange_return = Return(
                sale_id=sale_locked.id,
                processed_by=session['user_id'],
                refund_method=refund_method if refund_amount > 0 else 'exchange',
                total_refunded=refund_amount,
                note=note or None,
            )
            exchange_return.items.append(ReturnItem(
                sale_item_id=sale_item_locked.id,
                product_id=old_variant.product_id,
                quantity=qty,
                refund_amount=refund_amount,
                reason=f'Exchange return -> {new_variant.product.name} ({new_variant.size}/{new_variant.color})',
            ))
            db.session.add(exchange_return)

            exchange_invoice_number = generate_invoice_number(db.session)
            exchange_sale = Sale(
                invoice_number=exchange_invoice_number,
                cashier_id=session['user_id'],
                customer_id=sale_locked.customer_id,
                total_amount=new_line_subtotal,
                gst_total=new_line_gst,
                grand_total=new_line_total,
                payment_method=collect_method if difference > 0 else 'exchange',
            )
            db.session.add(exchange_sale)
            db.session.flush()

            db.session.add(SaleItem(
                sale_id=exchange_sale.id,
                variant_id=new_variant.id,
                quantity=qty,
                price_at_sale=new_unit_price,
                snapshot_size=new_variant.size,
                snapshot_color=new_variant.color,
                gst_percent=new_gst_percent,
                subtotal=new_line_subtotal,
                weight_kg=None,
                unit_label=None,
            ))

            exchange_credit = min(old_line_total, new_line_total).quantize(Decimal('0.01'))
            db.session.add(SalePayment(
                sale_id=exchange_sale.id,
                payment_method='exchange_credit',
                amount=exchange_credit,
            ))
            if difference > 0:
                db.session.add(SalePayment(
                    sale_id=exchange_sale.id,
                    payment_method=collect_method,
                    amount=difference,
                ))

            active_session = (
                db.session.query(CashSession)
                .filter(
                    CashSession.cashier_id == session['user_id'],
                    CashSession.end_time == None
                )
                .with_for_update()
                .first()
            )
            if active_session and difference != 0:
                active_session.system_total += difference

            reason_base = (
                f'Exchange {sale_locked.invoice_number} -> {exchange_sale.invoice_number}: '
                f'{old_variant.size}/{old_variant.color} -> {new_variant.size}/{new_variant.color}'
            )
            for product_id in sorted(product_by_id.keys()):
                db.session.add(InventoryLog(
                    product_id=product_id,
                    old_stock=stock_before[product_id],
                    new_stock=stock_after[product_id],
                    changed_by=session.get('user_id'),
                    reason=reason_base,
                ))

            exchange_return.note = (
                f'{note} | ' if note else ''
            ) + (
                f'Exchange invoice {exchange_sale.invoice_number}; old gross {old_line_total:.2f}, '
                f'new gross {new_line_total:.2f}, delta {difference:.2f}.'
            )

            exchange_sale.print_html = render_template(
                'billing/invoice.html',
                title=f'Invoice {exchange_sale.invoice_number}',
                sale=exchange_sale,
                reprint_mode=False,
            )

            db.session.commit()

            if difference > 0:
                flash(
                    f'Exchange complete. Collect Rs {difference:,.2f}. '
                    f'New invoice: {exchange_sale.invoice_number}.',
                    'success',
                )
            elif difference < 0:
                flash(
                    f'Exchange complete. Refund Rs {refund_amount:,.2f} via {refund_method}. '
                    f'New invoice: {exchange_sale.invoice_number}.',
                    'success',
                )
            else:
                flash(
                    f'Exchange complete. No balance due. New invoice: {exchange_sale.invoice_number}.',
                    'success',
                )

            return redirect(url_for('billing.invoice', sale_id=exchange_sale.id))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception(f'Exchange processing failed: {e}')
            flash('An unexpected error occurred during exchange.', 'error')

    return render_template(
        'billing/exchange/process.html',
        sale=sale,
        returnable_items=returnable_items,
        new_variants=new_variants,
    )


# ── RETURNS & REFUNDS ─────────────────────────────────────────────

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
    POST: Process the return atomically.
    """

    if request.method == 'POST':
        try:
            sale_locked = (
                db.session.query(Sale)
                .filter(Sale.id == sale_id)
                .with_for_update()
                .first()
            )
            if sale_locked is None:
                raise ValueError('Sale not found.')

            current_app.logger.info(
                f"Processing return for Sale {sale_locked.id} (Inv: {sale_locked.invoice_number})"
            )

            # ── Lock all sale items in a deterministic order ──────────
            # Returns can involve multiple items; locking by ID prevents deadlocks.
            # Use subquery to identify items and their variants.
            sale_items_to_lock = (
                db.session.query(SaleItem)
                .filter(SaleItem.sale_id == sale_locked.id)
                .order_by(SaleItem.id.asc())
                .with_for_update()
                .all()
            )
            
            # Identify variant IDs involved
            variant_ids = sorted({item.variant_id for item in sale_items_to_lock if item.variant_id})
            
            # Lock variants in ID order
            for vid in variant_ids:
                db.session.query(ProductVariant).filter(ProductVariant.id == vid).with_for_update().first()

            existing_return_items = (
                db.session.query(ReturnItem)
                .join(Return, ReturnItem.return_id == Return.id)
                .filter(Return.sale_id == sale_locked.id)
                .with_for_update()
                .all()
            )

            returned_map_tx = {}
            for ret_item in existing_return_items:
                returned_map_tx[ret_item.sale_item_id] = returned_map_tx.get(ret_item.sale_item_id, 0) + ret_item.quantity

            refund_method = request.form.get('refund_method')
            note = request.form.get('note')
            if not refund_method:
                raise ValueError('Refund method is required.')

            new_return = Return(
                sale_id=sale_locked.id,
                processed_by=session['user_id'],
                refund_method=refund_method,
                total_refunded=0,
                note=note,
            )

            total_refund = Decimal('0.00')
            items_returned = False

            for item in locked_items:
                qty_str = request.form.get(f'qty_{item.id}')
                if not qty_str:
                    continue

                try:
                    qty_to_return = int(qty_str)
                except ValueError:
                    continue

                if qty_to_return <= 0:
                    continue

                already_returned = returned_map_tx.get(item.id, 0)
                remaining = item.quantity - already_returned
                if qty_to_return > remaining:
                    raise ValueError(f'Cannot return {qty_to_return} of {item.product.name}. Only {remaining} eligible.')

                unit_refund = item.subtotal_with_gst / item.quantity
                line_refund = (unit_refund * qty_to_return).quantize(Decimal('0.01'))
                if item.variant is None:
                    raise ValueError(f'Variant for sale item {item.id} not found.')

                ret_line = ReturnItem(
                    sale_item_id=item.id,
                    product_id=item.variant.product_id,
                    quantity=qty_to_return,
                    refund_amount=line_refund,
                    reason='Customer Return',
                )
                new_return.items.append(ret_line)
                total_refund += line_refund
                items_returned = True
                returned_map_tx[item.id] = already_returned + qty_to_return

                # No need for second with_for_update() here as variants are already locked above
                variant = db.session.get(ProductVariant, item.variant_id)
                if variant is None:
                    raise ValueError(f'Variant {item.variant_id} not found.')

                variant.stock += qty_to_return

            if not items_returned:
                current_app.logger.warning(f'Return failed (No items selected) for {sale_locked.invoice_number}')
                flash('No items selected for return. Please enter a quantity > 0.', 'warning')
                return redirect(url_for('billing.returns_process', sale_id=sale_locked.id))

            new_return.total_refunded = total_refund
            db.session.add(new_return)
            db.session.commit()

            flash(f'Return processed successfully. Refund: Rs {total_refund:,.2f}', 'success')
            return redirect(url_for('billing.returns_process', sale_id=sale_locked.id))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception(f'Return processing failed: {e}')
            flash('An unexpected error occurred.', 'error')

    sale = db.session.get(Sale, sale_id)
    if not sale:
        flash('Sale not found.', 'error')
        return redirect(url_for('billing.returns_search'))

    returned_map = _build_returned_map(sale)
    return render_template(
        'billing/returns/process.html',
        sale=sale,
        returned_map=returned_map
    )




